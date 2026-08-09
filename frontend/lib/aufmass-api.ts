/**
 * Aufmaß API client — the layered pipeline (Plan → VOB-Menge → Export).
 *
 * Mirrors the backend contracts in app/domain/. Two fields drive the whole
 * review screen and are worth knowing before reading further:
 *
 *   is_exportable        false until a human has signed the position off. The
 *                        export button stays disabled while nothing qualifies.
 *   evidence[].geometry  where the number came from, in PDF points. This is what
 *                        lets a click on a position highlight the spot on the plan.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_SNAPGRID_API_URL || "http://localhost:8000";

const AUFMASS_BASE = `${API_BASE}/api/v1/aufmass`;

// ----------------------------------------------------------------------- types

export type PositionStatus = "auto" | "reviewed" | "corrected" | "manual";

export type ExtractionMethod =
  | "vector"
  | "text"
  | "table"
  | "derived"
  | "manual"
  | "ocr"
  | "cv";

export interface Geometry {
  /** Always "pdf_points" once it leaves the backend. */
  space: string;
  /** [x, y, width, height] in PDF points, origin top-left. */
  bbox: [number, number, number, number] | null;
  polygon: [number, number][] | null;
  dpi: number | null;
}

export interface Evidence {
  evidence_id: string;
  method: ExtractionMethod;
  file_id: string;
  page_number: number;
  geometry: Geometry | null;
  /** The literal string as it appeared in the plan, e.g. "NRF: 42,11". */
  raw_value: string | null;
  detector: string | null;
  confidence: number;
  /** True when a model interpreted pixels rather than read structured data. */
  is_interpretive: boolean;
  notes: string[];
}

export interface CalculationStep {
  label: string;
  expression: string;
  result: number;
  result_formatted: string;
  unit: string;
  note: string | null;
}

export interface Position {
  position_id: string;
  trade: string;
  trade_label: string;
  atv: string;
  designation: string;
  quantity: number;
  quantity_formatted: string;
  unit: string;
  kind: string;
  /** The geometric value before the ruleset applied deductions. */
  raw_quantity: number | null;
  raw_quantity_formatted: string | null;
  ruleset_id: string;
  ruleset_version: string;
  calculation: CalculationStep[];
  evidence: Evidence[];
  status: PositionStatus;
  needs_review: boolean;
  is_exportable: boolean;
  confidence: number;
  reviewed_by: string | null;
  reviewed_at: string | null;
  lv_position: string | null;
  warnings: string[];
  room_id: string | null;
  room_label: string | null;
}

/**
 * What the measuring tool needs to convert clicks into metres.
 *
 * `points_per_metre` is in PDF points, the same space evidence geometry uses.
 * Scale it by displayed-width / page-width to get pixels on screen.
 */
export interface MeasurementContext {
  scale_denominator: number | null;
  points_per_metre: number | null;
  is_scale_confirmed: boolean;
}

export interface PositionSet {
  job_id: string;
  measurement?: MeasurementContext;
  document_id: string;
  trade: string;
  trade_label: string;
  atv: string;
  ruleset_id: string | null;
  ruleset_version: string | null;
  positions: Position[];
  total_count: number;
  exportable_count: number;
  review_pending_count: number;
  is_release_ready: boolean;
  totals_by_unit: Record<string, number>;
  warnings: string[];
  created_at: string;
}

export interface TradeInfo {
  trade: string;
  label: string;
  atv: string;
  ruleset_id: string;
  version: string;
  description: string;
}

export interface UnverifiedThreshold {
  key: string;
  value: number;
  unit: string;
  atv: string;
  description: string;
  note: string;
}

export interface TradeCatalog {
  trades: TradeInfo[];
  unverified_thresholds: UnverifiedThreshold[];
  all_thresholds_verified: boolean;
}

export interface AnalyzeOptions {
  wallHeightM?: number;
  openingHeightM?: number;
  includeCeiling?: boolean;
  detectOpenings?: boolean;
}

/** Page image plus the numbers needed to place highlights on it. */
export interface PageImage {
  /** Object URL — revoke it when the component unmounts. */
  url: string;
  widthPoints: number;
  heightPoints: number;
  widthPx: number;
  heightPx: number;
  pageCount: number;
}

// --------------------------------------------------------------------- helpers

async function failWith(response: Response, fallback: string): Promise<never> {
  let detail = fallback;
  try {
    const body = await response.json();
    if (body?.detail) detail = body.detail;
  } catch {
    // Response had no JSON body — keep the fallback.
  }
  throw new Error(detail);
}

// ------------------------------------------------------------------- endpoints

/** Which trades have a ruleset, and which norm values are still unverified. */
export async function getTrades(): Promise<TradeCatalog> {
  const response = await fetch(`${AUFMASS_BASE}/trades`);
  if (!response.ok) await failWith(response, "Gewerke konnten nicht geladen werden.");
  return response.json();
}

/** Upload a plan and calculate positions. Nothing comes back reviewed. */
export async function analyzePlan(
  file: File,
  trade: string,
  options: AnalyzeOptions = {}
): Promise<PositionSet> {
  const form = new FormData();
  form.append("file", file);
  form.append("trade", trade);
  if (options.wallHeightM != null)
    form.append("wall_height_m", String(options.wallHeightM));
  if (options.openingHeightM != null)
    form.append("opening_height_m", String(options.openingHeightM));
  form.append("include_ceiling", String(options.includeCeiling ?? false));
  form.append("detect_openings", String(options.detectOpenings ?? false));

  const response = await fetch(`${AUFMASS_BASE}/analyze`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) await failWith(response, "Analyse fehlgeschlagen.");
  return response.json();
}

export async function getResult(jobId: string): Promise<PositionSet> {
  const response = await fetch(`${AUFMASS_BASE}/${jobId}`);
  if (!response.ok) await failWith(response, "Aufmaß nicht gefunden.");
  return response.json();
}

/** Sign off on one position. Pass a quantity to record a correction instead. */
export async function reviewPosition(
  jobId: string,
  positionId: string,
  reviewedBy: string,
  correctedQuantity?: number
): Promise<{
  position: Position;
  exportable_count: number;
  review_pending_count: number;
  is_release_ready: boolean;
}> {
  const response = await fetch(
    `${AUFMASS_BASE}/${jobId}/positions/${positionId}/review`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewed_by: reviewedBy,
        corrected_quantity: correctedQuantity ?? null,
      }),
    }
  );
  if (!response.ok) await failWith(response, "Freigabe fehlgeschlagen.");
  return response.json();
}

/**
 * Sign off on everything still open.
 *
 * `onlyWithoutWarnings` defaults to true on the backend — a bulk approval must
 * not silently wave through positions the system flagged.
 */
export async function reviewAll(
  jobId: string,
  reviewedBy: string,
  onlyWithoutWarnings = true
): Promise<{
  approved: number;
  skipped_with_warnings: number;
  exportable_count: number;
  review_pending_count: number;
  is_release_ready: boolean;
}> {
  const response = await fetch(`${AUFMASS_BASE}/${jobId}/review-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      reviewed_by: reviewedBy,
      only_without_warnings: onlyWithoutWarnings,
    }),
  });
  if (!response.ok) await failWith(response, "Sammelfreigabe fehlgeschlagen.");
  return response.json();
}

/**
 * Fetch a rendered plan page.
 *
 * Uses fetch rather than an <img src> because the placement of every highlight
 * depends on headers an image tag cannot expose — the page's size in PDF points
 * versus its rendered pixel size.
 */
export async function getPageImage(
  jobId: string,
  pageNumber: number,
  maxPx = 2400
): Promise<PageImage> {
  const response = await fetch(
    `${AUFMASS_BASE}/${jobId}/page/${pageNumber}?max_px=${maxPx}`
  );
  if (!response.ok) await failWith(response, "Planseite konnte nicht geladen werden.");

  const blob = await response.blob();
  return {
    url: URL.createObjectURL(blob),
    widthPoints: Number(response.headers.get("X-Page-Width-Points") ?? 0),
    heightPoints: Number(response.headers.get("X-Page-Height-Points") ?? 0),
    widthPx: Number(response.headers.get("X-Image-Width-Px") ?? 0),
    heightPx: Number(response.headers.get("X-Image-Height-Px") ?? 0),
    pageCount: Number(response.headers.get("X-Page-Count") ?? 1),
  };
}

export type ExportFormat = "xlsx" | "csv" | "protokoll";

/**
 * Download the Aufmaß.
 *
 * The backend answers 409 when nothing is signed off; the thrown message
 * explains what is missing, so show it verbatim.
 */
export async function downloadExport(
  jobId: string,
  format: ExportFormat,
  documentId: string
): Promise<void> {
  const response = await fetch(`${AUFMASS_BASE}/${jobId}/export?format=${format}`);
  if (!response.ok) await failWith(response, "Export fehlgeschlagen.");

  const blob = await response.blob();
  const extension = format === "protokoll" ? "txt" : format;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${documentId}_aufmass.${extension}`;
  link.click();
  URL.revokeObjectURL(link.href);
}
