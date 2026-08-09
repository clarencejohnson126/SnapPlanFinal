"use client";

/**
 * Aufmaß — upload, then review.
 *
 * The review half is the product. Everything here serves one loop: read a
 * proposed quantity, see how it was derived, look at the spot on the plan it
 * came from, then approve or correct it. A number the user cannot trace is a
 * number they will not sign, so the derivation and the plan position are never
 * more than one click away.
 *
 * Highlights are positioned in percent of the page's PDF-point dimensions
 * rather than in pixels. That keeps them correct at any zoom or window size —
 * the one bug class that would quietly destroy trust in the whole screen.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Download,
  FileText,
  Loader2,
  MapPin,
  Pencil,
  Ruler,
  Upload,
} from "lucide-react";

import {
  analyzePlan,
  downloadExport,
  getPageImage,
  getResult,
  getTrades,
  reviewAll,
  reviewPosition,
  type ExportFormat,
  type PageImage,
  type Position,
  type PositionSet,
  type TradeCatalog,
} from "@/lib/aufmass-api";

const ACCENT = "#00D4AA";

export default function AufmassPage() {
  const [catalog, setCatalog] = useState<TradeCatalog | null>(null);
  const [result, setResult] = useState<PositionSet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTrades().then(setCatalog).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="max-w-[1800px] mx-auto p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-white">Aufmaß</h1>
        <p className="text-[#94A3B8] mt-1">
          Mengen nach VOB/C — jede Zahl mit Herleitung und Fundstelle im Plan.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-200">
          {error}
        </div>
      )}

      {!result ? (
        <UploadPanel
          catalog={catalog}
          onResult={(r) => {
            setError(null);
            setResult(r);
          }}
          onError={setError}
        />
      ) : (
        <ReviewScreen
          result={result}
          onResult={setResult}
          onError={setError}
          onReset={() => setResult(null)}
        />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------- upload

function UploadPanel({
  catalog,
  onResult,
  onError,
}: {
  catalog: TradeCatalog | null;
  onResult: (r: PositionSet) => void;
  onError: (m: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [trade, setTrade] = useState("");
  const [wallHeight, setWallHeight] = useState("");
  const [openingHeight, setOpeningHeight] = useState("2.01");
  const [includeCeiling, setIncludeCeiling] = useState(false);
  const [detectOpenings, setDetectOpenings] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (catalog?.trades.length && !trade) setTrade(catalog.trades[0].trade);
  }, [catalog, trade]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    onDrop: (files) => files[0] && setFile(files[0]),
  });

  const run = async () => {
    if (!file || !trade) return;
    setBusy(true);
    try {
      onResult(
        await analyzePlan(file, trade, {
          wallHeightM: wallHeight ? Number(wallHeight) : undefined,
          openingHeightM: openingHeight ? Number(openingHeight) : undefined,
          includeCeiling,
          detectOpenings,
        })
      );
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div
        {...getRootProps()}
        className={`rounded-xl border-2 border-dashed p-12 text-center cursor-pointer transition-colors ${
          isDragActive
            ? "border-[#00D4AA] bg-[#00D4AA]/5"
            : "border-white/15 hover:border-white/30"
        }`}
      >
        <input {...getInputProps()} />
        {file ? (
          <>
            <FileText className="w-10 h-10 mx-auto mb-3" style={{ color: ACCENT }} />
            <p className="text-white font-medium">{file.name}</p>
            <p className="text-[#94A3B8] text-sm mt-1">
              {(file.size / 1024 / 1024).toFixed(1)} MB — zum Ersetzen klicken
            </p>
          </>
        ) : (
          <>
            <Upload className="w-10 h-10 mx-auto mb-3 text-[#94A3B8]" />
            <p className="text-white font-medium">Plan hierher ziehen</p>
            <p className="text-[#94A3B8] text-sm mt-1">PDF, ein Plan pro Analyse</p>
          </>
        )}
      </div>

      <div className="rounded-xl border border-white/10 p-6 space-y-5">
        <Field label="Gewerk">
          <select
            value={trade}
            onChange={(e) => setTrade(e.target.value)}
            className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2.5 text-white"
          >
            {catalog?.trades.map((t) => (
              <option key={t.trade} value={t.trade} className="bg-[#0F1B2A]">
                {t.label} — {t.atv}
              </option>
            ))}
          </select>
          {catalog?.trades.length === 0 && (
            <p className="text-amber-300/80 text-sm mt-2">Kein Regelwerk registriert.</p>
          )}
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Raumhöhe (m)" hint="falls der Plan keine enthält">
            <input
              type="number"
              step="0.01"
              value={wallHeight}
              onChange={(e) => setWallHeight(e.target.value)}
              placeholder="z. B. 2,75"
              className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2.5 text-white"
            />
          </Field>
          <Field label="Türhöhe (m)" hint="für Öffnungen ohne Maß">
            <input
              type="number"
              step="0.01"
              value={openingHeight}
              onChange={(e) => setOpeningHeight(e.target.value)}
              className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2.5 text-white"
            />
          </Field>
        </div>

        <Toggle
          checked={includeCeiling}
          onChange={setIncludeCeiling}
          label="Deckenflächen mitrechnen"
        />
        <Toggle
          checked={detectOpenings}
          onChange={setDetectOpenings}
          label="Öffnungen aus der Plangeometrie erkennen"
          hint="Langsamer. Nur nötig, wenn der Plan keine Türstempel hat."
        />

        {catalog && !catalog.all_thresholds_verified && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200/90">
            <div className="flex gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                {catalog.unverified_thresholds.length} Normwerte sind noch nicht gegen
                die gedruckte VOB/C geprüft. Ergebnisse eignen sich zur Vorschau, noch
                nicht zur Abrechnung.
              </span>
            </div>
          </div>
        )}

        <button
          onClick={run}
          disabled={!file || !trade || busy}
          className="w-full inline-flex items-center justify-center gap-2 rounded-lg px-4 py-3 font-semibold text-[#0F1B2A] disabled:opacity-40 transition-opacity"
          style={{ backgroundColor: ACCENT }}
        >
          {busy ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <FileText className="w-5 h-5" />
          )}
          {busy ? "Wird analysiert…" : "Aufmaß erstellen"}
        </button>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-white mb-1.5">
        {label}
        {hint && <span className="text-[#94A3B8] font-normal"> — {hint}</span>}
      </label>
      {children}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 w-4 h-4 accent-[#00D4AA]"
      />
      <span>
        <span className="text-white text-sm">{label}</span>
        {hint && <span className="block text-[#94A3B8] text-xs mt-0.5">{hint}</span>}
      </span>
    </label>
  );
}

// ----------------------------------------------------------------------- review

function ReviewScreen({
  result,
  onResult,
  onError,
  onReset,
}: {
  result: PositionSet;
  onResult: (r: PositionSet) => void;
  onError: (m: string) => void;
  onReset: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(
    result.positions[0]?.position_id ?? null
  );
  const [page, setPage] = useState<PageImage | null>(null);
  const [busy, setBusy] = useState(false);
  const [measuring, setMeasuring] = useState(false);
  const [measurement, setMeasurement] = useState<Measurement | null>(null);

  const pointsPerMetre = result.measurement?.points_per_metre ?? null;

  const selected = useMemo(
    () => result.positions.find((p) => p.position_id === selectedId) ?? null,
    [result.positions, selectedId]
  );

  useEffect(() => {
    let stale = false;
    let created: string | null = null;

    getPageImage(result.job_id, 1)
      .then((img) => {
        if (stale) {
          URL.revokeObjectURL(img.url);
          return;
        }
        created = img.url;
        setPage(img);
      })
      .catch((e) => onError(e.message));

    return () => {
      stale = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [result.job_id, onError]);

  /** Replace one position in place, keeping the counters honest. */
  const applyPosition = useCallback(
    (
      updated: Position,
      counts: {
        exportable_count: number;
        review_pending_count: number;
        is_release_ready: boolean;
      }
    ) => {
      onResult({
        ...result,
        positions: result.positions.map((p) =>
          p.position_id === updated.position_id ? updated : p
        ),
        ...counts,
      });
    },
    [result, onResult]
  );

  const approve = async (position: Position, corrected?: number) => {
    setBusy(true);
    try {
      const response = await reviewPosition(
        result.job_id,
        position.position_id,
        "Nutzer",
        corrected
      );
      applyPosition(response.position, response);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const approveAll = async () => {
    setBusy(true);
    try {
      const response = await reviewAll(result.job_id, "Nutzer", true);
      onResult(await getResult(result.job_id));
      if (response.skipped_with_warnings > 0) {
        onError(
          `${response.approved} freigegeben. ${response.skipped_with_warnings} Positionen ` +
            `mit Hinweisen wurden übersprungen und müssen einzeln geprüft werden.`
        );
      }
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const exportAs = async (format: ExportFormat) => {
    try {
      await downloadExport(result.job_id, format, result.document_id);
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <ReviewHeader
        result={result}
        busy={busy}
        onApproveAll={approveAll}
        onExport={exportAs}
        onReset={onReset}
      />

      <div className="grid lg:grid-cols-[1fr_460px] gap-4 items-start">
        <div className="space-y-2">
          <MeasureBar
            measuring={measuring}
            measurement={measurement}
            pointsPerMetre={pointsPerMetre}
            scaleDenominator={result.measurement?.scale_denominator ?? null}
            onToggle={() => {
              setMeasuring((v) => !v);
              setMeasurement(null);
            }}
          />
          <PlanView
            page={page}
            selected={selected}
            pointsPerMetre={pointsPerMetre}
            measuring={measuring}
            measurement={measurement}
            onMeasured={setMeasurement}
          />
        </div>
        <PositionList
          positions={result.positions}
          selectedId={selectedId}
          busy={busy}
          onSelect={setSelectedId}
          onApprove={approve}
        />
      </div>
    </div>
  );
}

function ReviewHeader({
  result,
  busy,
  onApproveAll,
  onExport,
  onReset,
}: {
  result: PositionSet;
  busy: boolean;
  onApproveAll: () => void;
  onExport: (f: ExportFormat) => void;
  onReset: () => void;
}) {
  const canExport = result.exportable_count > 0;

  return (
    <div className="rounded-xl border border-white/10 p-4 flex flex-wrap items-center gap-4 justify-between">
      <div>
        <h2 className="text-white font-semibold">{result.document_id}</h2>
        <p className="text-[#94A3B8] text-sm">
          {result.trade_label} · VOB/C ATV {result.atv} · Regelwerk {result.ruleset_id} v
          {result.ruleset_version}
        </p>
      </div>

      <div className="flex items-center gap-5 text-sm">
        <Counter value={result.total_count} label="Positionen" />
        <Counter value={result.exportable_count} label="freigegeben" color={ACCENT} />
        <Counter
          value={result.review_pending_count}
          label="offen"
          color={result.review_pending_count ? "#F59E0B" : undefined}
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onReset}
          className="px-3 py-2 rounded-lg border border-white/10 text-[#94A3B8] hover:text-white text-sm"
        >
          Neuer Plan
        </button>
        <button
          onClick={onApproveAll}
          disabled={busy || !result.review_pending_count}
          className="px-3 py-2 rounded-lg border border-white/10 text-white text-sm disabled:opacity-40"
        >
          {busy ? "…" : "Alle ohne Hinweis freigeben"}
        </button>
        {(["xlsx", "csv", "protokoll"] as ExportFormat[]).map((f) => (
          <button
            key={f}
            onClick={() => onExport(f)}
            disabled={!canExport}
            title={canExport ? undefined : "Erst Positionen freigeben"}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-[#0F1B2A] disabled:opacity-30"
            style={{ backgroundColor: ACCENT }}
          >
            <Download className="w-4 h-4" />
            {f === "protokoll" ? "Protokoll" : f.toUpperCase()}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * The measuring toolbar.
 *
 * Shows the scale it is working from, because a measurement is only as good as
 * that number — and if the plan states none, the tool says so instead of
 * quietly returning zeroes.
 */
function MeasureBar({
  measuring,
  measurement,
  pointsPerMetre,
  scaleDenominator,
  onToggle,
}: {
  measuring: boolean;
  measurement: Measurement | null;
  pointsPerMetre: number | null;
  scaleDenominator: number | null;
  onToggle: () => void;
}) {
  const usable = pointsPerMetre != null;

  return (
    <div className="rounded-xl border border-white/10 px-4 py-2.5 flex flex-wrap items-center gap-3 text-sm">
      <button
        onClick={onToggle}
        disabled={!usable}
        title={usable ? undefined : "Kein Maßstab im Plan erkannt"}
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg font-medium transition-colors disabled:opacity-40 ${
          measuring ? "text-[#0F1B2A]" : "border border-white/10 text-white"
        }`}
        style={measuring ? { backgroundColor: "#F59E0B" } : undefined}
      >
        <Ruler className="w-4 h-4" />
        {measuring ? "Messen beenden" : "Im Plan messen"}
      </button>

      {scaleDenominator ? (
        <span className="text-[#94A3B8]">
          Maßstab 1:{scaleDenominator}
        </span>
      ) : (
        <span className="text-amber-300/90">
          Kein Maßstab erkannt — Messen nicht möglich
        </span>
      )}

      {measuring && !measurement && (
        <span className="text-[#94A3B8]">
          Zwei Punkte im Plan anklicken
        </span>
      )}

      {measurement && (
        <span className="font-semibold" style={{ color: "#F59E0B" }}>
          Gemessen: {measurement.metres.toFixed(3).replace(".", ",")} m
        </span>
      )}
    </div>
  );
}

function Counter({
  value,
  label,
  color,
}: {
  value: number;
  label: string;
  color?: string;
}) {
  return (
    <span className="whitespace-nowrap">
      <strong className="text-lg" style={{ color: color ?? "#fff" }}>
        {value}
      </strong>{" "}
      <span className="text-[#94A3B8]">{label}</span>
    </span>
  );
}

/**
 * A distance the user measured by clicking two points on the plan.
 *
 * Kept in percent of the page so the marker survives zooming, exactly like the
 * evidence highlights.
 */
interface Measurement {
  from: { xPct: number; yPct: number };
  to: { xPct: number; yPct: number };
  metres: number;
}

/**
 * The plan, with highlights and a ruler.
 *
 * Highlight coordinates come from evidence geometry in PDF points and are
 * converted to percentages of the page. Percent rather than pixels means the
 * marker stays on target no matter how the image is scaled.
 *
 * MEASURING
 *
 * Two clicks give a distance. The conversion is pure arithmetic: the click
 * positions are known as a fraction of the page, the page's size in PDF points
 * is known, and the scale says how many points make a metre. Nothing is
 * estimated — this is the same calculation a Kalkulator does with a scale ruler,
 * which is why it can replace a value the plan does not state.
 */
function PlanView({
  page,
  selected,
  pointsPerMetre,
  measuring,
  measurement,
  onMeasured,
}: {
  page: PageImage | null;
  selected: Position | null;
  pointsPerMetre: number | null;
  measuring: boolean;
  measurement: Measurement | null;
  onMeasured: (m: Measurement | null) => void;
}) {
  const [pending, setPending] = useState<{ xPct: number; yPct: number } | null>(null);

  const handleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!measuring || !page) return;

    const box = event.currentTarget.getBoundingClientRect();
    const xPct = ((event.clientX - box.left) / box.width) * 100;
    const yPct = ((event.clientY - box.top) / box.height) * 100;

    if (!pending) {
      setPending({ xPct, yPct });
      onMeasured(null);
      return;
    }

    // Percent → PDF points → metres. Each axis uses its own page dimension,
    // because a sheet is not square and one factor would skew diagonals.
    const dxPoints = ((xPct - pending.xPct) / 100) * page.widthPoints;
    const dyPoints = ((yPct - pending.yPct) / 100) * page.heightPoints;
    const distancePoints = Math.hypot(dxPoints, dyPoints);
    const metres = pointsPerMetre ? distancePoints / pointsPerMetre : 0;

    onMeasured({ from: pending, to: { xPct, yPct }, metres });
    setPending(null);
  };
  const marks = useMemo(() => {
    if (!page || !selected) return [];
    return selected.evidence
      .filter((e) => e.geometry?.bbox)
      .map((e) => {
        const [x, y, w, h] = e.geometry!.bbox!;
        return {
          id: e.evidence_id,
          left: (x / page.widthPoints) * 100,
          top: (y / page.heightPoints) * 100,
          width: (w / page.widthPoints) * 100,
          height: (h / page.heightPoints) * 100,
        };
      });
  }, [page, selected]);

  if (!page) {
    return (
      <div className="rounded-xl border border-white/10 h-[70vh] grid place-items-center">
        <Loader2 className="w-8 h-8 animate-spin text-[#94A3B8]" />
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 overflow-auto max-h-[78vh] bg-white">
      <div
        className={`relative inline-block min-w-full ${measuring ? "cursor-crosshair" : ""}`}
        onClick={handleClick}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={page.url} alt="Planseite" className="block w-full" draggable={false} />

        {/* First click of a pending measurement. */}
        {pending && (
          <div
            className="absolute pointer-events-none rounded-full"
            style={{
              left: `${pending.xPct}%`,
              top: `${pending.yPct}%`,
              width: 10,
              height: 10,
              marginLeft: -5,
              marginTop: -5,
              background: "#F59E0B",
            }}
          />
        )}

        {/* A completed measurement: the line plus its length. */}
        {measurement && (
          <>
            <svg
              className="absolute inset-0 w-full h-full pointer-events-none"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
            >
              <line
                x1={measurement.from.xPct}
                y1={measurement.from.yPct}
                x2={measurement.to.xPct}
                y2={measurement.to.yPct}
                stroke="#F59E0B"
                strokeWidth={0.25}
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <div
              className="absolute pointer-events-none px-2 py-1 rounded text-xs font-semibold whitespace-nowrap"
              style={{
                left: `${(measurement.from.xPct + measurement.to.xPct) / 2}%`,
                top: `${(measurement.from.yPct + measurement.to.yPct) / 2}%`,
                transform: "translate(-50%, -140%)",
                background: "#F59E0B",
                color: "#0F1B2A",
              }}
            >
              {measurement.metres.toFixed(3).replace(".", ",")} m
            </div>
          </>
        )}

        {marks.map((m) => (
          <div key={m.id}>
            {/* Exact bounds of the source value. */}
            <div
              className="absolute pointer-events-none"
              style={{
                left: `${m.left}%`,
                top: `${m.top}%`,
                width: `${m.width}%`,
                height: `${m.height}%`,
                outline: `2px solid ${ACCENT}`,
                background: `${ACCENT}33`,
              }}
            />
            {/* A fixed-size ring, because a room stamp on an A0 sheet is well
                under one percent of the page and would otherwise be invisible. */}
            <div
              className="absolute pointer-events-none rounded-full animate-pulse"
              style={{
                left: `${m.left + m.width / 2}%`,
                top: `${m.top + m.height / 2}%`,
                width: 56,
                height: 56,
                marginLeft: -28,
                marginTop: -28,
                border: `2px solid ${ACCENT}`,
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function PositionList({
  positions,
  selectedId,
  busy,
  onSelect,
  onApprove,
}: {
  positions: Position[];
  selectedId: string | null;
  busy: boolean;
  onSelect: (id: string) => void;
  onApprove: (p: Position, corrected?: number) => void;
}) {
  return (
    <div className="rounded-xl border border-white/10 divide-y divide-white/5 overflow-y-auto max-h-[78vh]">
      {positions.map((position) => (
        <PositionRow
          key={position.position_id}
          position={position}
          expanded={position.position_id === selectedId}
          busy={busy}
          onSelect={() => onSelect(position.position_id)}
          onApprove={onApprove}
        />
      ))}
    </div>
  );
}

function PositionRow({
  position,
  expanded,
  busy,
  onSelect,
  onApprove,
}: {
  position: Position;
  expanded: boolean;
  busy: boolean;
  onSelect: () => void;
  onApprove: (p: Position, corrected?: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(position.quantity));

  const signedOff = position.is_exportable;

  return (
    <div className={expanded ? "bg-white/[0.03]" : ""}>
      <button
        onClick={onSelect}
        className="w-full text-left p-3 flex items-start gap-3 hover:bg-white/[0.02]"
      >
        <span className="mt-0.5">
          {signedOff ? (
            <Check className="w-4 h-4" style={{ color: ACCENT }} />
          ) : position.warnings.length ? (
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-[#94A3B8]" />
          )}
        </span>

        <span className="flex-1 min-w-0">
          <span className="block text-white text-sm truncate">
            {position.designation}
          </span>
          <span className="block text-[#94A3B8] text-xs mt-0.5">
            {position.status === "corrected" && "korrigiert · "}
            {position.warnings.length > 0 && `${position.warnings.length} Hinweise`}
          </span>
        </span>

        <span className="text-right shrink-0">
          <span className="block text-white font-semibold tabular-nums">
            {position.quantity_formatted} {position.unit}
          </span>
          {position.raw_quantity_formatted &&
            position.raw_quantity !== position.quantity && (
              <span className="block text-[#94A3B8] text-xs line-through tabular-nums">
                {position.raw_quantity_formatted}
              </span>
            )}
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-3">
          <div className="rounded-lg bg-black/30 p-3 font-mono text-xs text-[#94A3B8] space-y-1">
            {position.calculation.map((step, i) => (
              <div key={i}>
                <span className="text-white">{step.label}:</span> {step.expression} ={" "}
                <span className="text-white">
                  {step.result_formatted} {step.unit}
                </span>
                {step.note && (
                  <span className="block pl-3 opacity-70">({step.note})</span>
                )}
              </div>
            ))}
          </div>

          {position.evidence.some((e) => e.geometry) && (
            <p className="text-xs text-[#94A3B8] flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5" />
              Fundstelle auf Seite{" "}
              {[...new Set(position.evidence.map((e) => e.page_number))].join(", ")} — im
              Plan markiert
            </p>
          )}

          {position.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-300/90 flex gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              {w}
            </p>
          ))}

          {!signedOff && (
            <div className="flex items-center gap-2">
              {editing ? (
                <>
                  <input
                    type="number"
                    step="0.01"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    className="w-28 rounded-lg bg-white/5 border border-white/10 px-2 py-1.5 text-white text-sm tabular-nums"
                  />
                  <button
                    onClick={() => onApprove(position, Number(draft))}
                    disabled={busy}
                    className="px-3 py-1.5 rounded-lg text-sm font-medium text-[#0F1B2A]"
                    style={{ backgroundColor: ACCENT }}
                  >
                    Korrektur übernehmen
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="px-3 py-1.5 rounded-lg text-sm text-[#94A3B8]"
                  >
                    Abbrechen
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => onApprove(position)}
                    disabled={busy}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-[#0F1B2A] disabled:opacity-40"
                    style={{ backgroundColor: ACCENT }}
                  >
                    <Check className="w-4 h-4" />
                    Freigeben
                  </button>
                  <button
                    onClick={() => {
                      setDraft(String(position.quantity));
                      setEditing(true);
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 text-white text-sm"
                  >
                    <Pencil className="w-4 h-4" />
                    Korrigieren
                  </button>
                </>
              )}
            </div>
          )}

          {signedOff && position.reviewed_by && (
            <p className="text-xs" style={{ color: ACCENT }}>
              Freigegeben von {position.reviewed_by}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
