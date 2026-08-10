"""
Persistence for Aufmaß results.

WHY THIS EXISTS

`app/api/aufmass.py` kept results in a module-level dict. That works until the
process restarts — and on Render a cold start does exactly that, so a reviewer
who had signed off forty positions would come back to an empty screen. It also
breaks the moment a second worker serves a request, because the two processes
would not see each other's jobs.

WHY IT DEGRADES INSTEAD OF FAILING

If Supabase is unreachable — paused free-tier project, network hiccup — the
store falls back to memory rather than refusing the request. A user who cannot
save is still better off than one who cannot work at all, and `is_persistent`
lets the caller say so honestly instead of pretending the result is safe.

Table names carry the snapplan_ prefix: the database is shared with another
product that already has `jobs` and `profiles`.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import logging
import uuid

from app.domain.evidence import Evidence
from app.domain.position import CalculationStep, Position, PositionSet, PositionStatus
from app.domain.quantities import QuantityKind
from app.domain.trades import Trade

logger = logging.getLogger(__name__)

_JOBS_TABLE = "snapplan_aufmass_jobs"
_POSITIONS_TABLE = "snapplan_aufmass_positions"


@dataclass
class StoredJob:
    """A result plus what the review screen needs alongside it."""

    job_id: str
    positions: PositionSet
    pdf_path: Path
    scale_denominator: Optional[int] = None
    is_persistent: bool = True


class AufmassStore:
    """
    Saves and loads Aufmaß jobs.

    One instance per process. Supabase is contacted lazily so importing this
    module never blocks startup on a network call.
    """

    def __init__(self) -> None:
        self._memory: Dict[str, StoredJob] = {}
        self._client: Any = None
        self._client_ready = False

    # -------------------------------------------------------------- client

    def _supabase(self) -> Any:
        """The Supabase client, or None when unconfigured or unreachable."""
        if self._client_ready:
            return self._client

        self._client_ready = True
        try:
            from app.core.config import settings
            from supabase import create_client

            url = getattr(settings, "aufmass_supabase_url", None)
            key = getattr(settings, "aufmass_supabase_service_key", None)
            if not url or not key:
                logger.info("Aufmaß-Persistenz nicht konfiguriert — nutze Arbeitsspeicher.")
                return None

            self._client = create_client(url, key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase nicht verfügbar (%s) — nutze Arbeitsspeicher.", exc)
            self._client = None

        return self._client

    @property
    def is_persistent(self) -> bool:
        """Whether results actually survive a restart."""
        return self._supabase() is not None

    # --------------------------------------------------------------- write

    def save(self, position_set: PositionSet, pdf_path: Path,
             scale_denominator: Optional[int] = None) -> StoredJob:
        """Store a fresh result and return it with its id."""
        job_id = str(uuid.uuid4())
        job = StoredJob(
            job_id=job_id,
            positions=position_set,
            pdf_path=pdf_path,
            scale_denominator=scale_denominator,
            is_persistent=False,
        )

        # Always keep it in memory too: the plan file lives on local disk, so the
        # page-rendering endpoint needs the path even when the row is in Supabase.
        self._memory[job_id] = job

        client = self._supabase()
        if client is None:
            return job

        try:
            client.table(_JOBS_TABLE).insert({
                "id": job_id,
                "document_id": position_set.document_id,
                "trade": position_set.trade.value,
                "ruleset_id": position_set.ruleset_id,
                "ruleset_version": position_set.ruleset_version,
                "scale_denominator": scale_denominator,
                "scale_confirmed": False,
                "warnings": position_set.warnings,
                "plan_storage_path": str(pdf_path),
            }).execute()

            rows = [self._position_row(job_id, p) for p in position_set.positions]
            if rows:
                client.table(_POSITIONS_TABLE).insert(rows).execute()

            job.is_persistent = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Aufmaß %s konnte nicht gespeichert werden: %s", job_id, exc)

        return job

    def update_position(self, job_id: str, position: Position) -> None:
        """Persist a single position after review or correction."""
        client = self._supabase()
        if client is None:
            return

        try:
            client.table(_POSITIONS_TABLE).update({
                "quantity": position.quantity,
                "raw_quantity": position.raw_quantity,
                "calculation": [c.to_dict() for c in position.calculation],
                "warnings": position.warnings,
                "status": position.status.value,
                "reviewed_by": position.reviewed_by,
                "reviewed_at": (
                    position.reviewed_at.isoformat() if position.reviewed_at else None
                ),
            }).eq("job_id", job_id).eq("position_id", position.position_id).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Position %s nicht gespeichert: %s", position.position_id, exc)

    # ---------------------------------------------------------------- read

    def load(self, job_id: str) -> Optional[StoredJob]:
        """
        Fetch a job. Memory first — it holds the plan path this process needs.

        A job restored from the database after a restart has no local plan file,
        so page rendering will fail for it. The caller reports that rather than
        hiding it; the positions themselves are intact.
        """
        cached = self._memory.get(job_id)
        if cached is not None:
            return cached

        client = self._supabase()
        if client is None:
            return None

        try:
            job_rows = (
                client.table(_JOBS_TABLE).select("*").eq("id", job_id).execute().data
            )
            if not job_rows:
                return None
            row = job_rows[0]

            position_rows = (
                client.table(_POSITIONS_TABLE)
                .select("*").eq("job_id", job_id)
                .order("created_at").execute().data
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Aufmaß %s konnte nicht geladen werden: %s", job_id, exc)
            return None

        trade = Trade(row["trade"])
        position_set = PositionSet(
            document_id=row["document_id"],
            trade=trade,
            ruleset_id=row.get("ruleset_id"),
            ruleset_version=row.get("ruleset_version"),
            warnings=row.get("warnings") or [],
            positions=[
                self._position_from_row(r, trade, row) for r in position_rows
            ],
        )

        job = StoredJob(
            job_id=job_id,
            positions=position_set,
            pdf_path=Path(row.get("plan_storage_path") or ""),
            scale_denominator=row.get("scale_denominator"),
        )
        self._memory[job_id] = job
        return job

    # ------------------------------------------------------------- mapping

    @staticmethod
    def _position_row(job_id: str, position: Position) -> Dict[str, Any]:
        return {
            "job_id": job_id,
            "position_id": position.position_id,
            "designation": position.designation,
            "quantity": position.quantity,
            "unit": position.unit,
            "kind": position.kind.value,
            "raw_quantity": position.raw_quantity,
            "calculation": [c.to_dict() for c in position.calculation],
            "evidence": [e.to_dict() for e in position.evidence],
            "warnings": position.warnings,
            "status": position.status.value,
            "reviewed_by": position.reviewed_by,
            "reviewed_at": (
                position.reviewed_at.isoformat() if position.reviewed_at else None
            ),
            "room_id": position.room_id,
            "room_label": position.room_label,
            "lv_position": position.lv_position,
        }

    @staticmethod
    def _position_from_row(row: Dict[str, Any], trade: Trade,
                           job_row: Dict[str, Any]) -> Position:
        """
        Rebuild a Position from its row.

        Trade and ruleset come from the job row rather than being duplicated on
        every position — they are properties of the run, not of the line item.
        """
        reviewed_at = None
        if row.get("reviewed_at"):
            reviewed_at = datetime.fromisoformat(
                str(row["reviewed_at"]).replace("Z", "+00:00")
            )

        return Position(
            trade=trade,
            designation=row["designation"],
            quantity=float(row["quantity"]),
            kind=QuantityKind(row["kind"]),
            ruleset_id=job_row.get("ruleset_id") or "",
            ruleset_version=job_row.get("ruleset_version") or "",
            calculation=[
                CalculationStep(
                    label=c.get("label", ""),
                    expression=c.get("expression", ""),
                    result=c.get("result", 0.0),
                    unit=c.get("unit", ""),
                    note=c.get("note"),
                )
                for c in (row.get("calculation") or [])
            ],
            evidence=[Evidence.from_dict(e) for e in (row.get("evidence") or [])],
            raw_quantity=(
                float(row["raw_quantity"])
                if row.get("raw_quantity") is not None else None
            ),
            status=PositionStatus(row.get("status", "auto")),
            reviewed_by=row.get("reviewed_by"),
            reviewed_at=reviewed_at,
            lv_position=row.get("lv_position"),
            warnings=row.get("warnings") or [],
            room_id=row.get("room_id"),
            room_label=row.get("room_label"),
            position_id=row["position_id"],
        )


#: Process-wide store. One instance suffices; it holds no per-request state.
store = AufmassStore()
