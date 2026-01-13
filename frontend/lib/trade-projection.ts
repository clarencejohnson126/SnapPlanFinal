/**
 * Trade Material Projection - TypeScript Types and API Client
 *
 * This module provides types and API functions for the trade material
 * projection system. It separates ground truth (measured) from projections (estimates).
 */

// ==================
// TYPES
// ==================

export type TradeType =
  | 'scaffolding'
  | 'drywall'
  | 'screed'
  | 'floor_finish'
  | 'waterproofing';

export type ProjectionMethod = 'rule_based' | 'llm_assisted';

export type ConfidenceLevel = 'high' | 'medium' | 'low';

/**
 * Reference to a measurement from the extraction result.
 * Used for traceability.
 */
export interface GroundTruthMeasurement {
  measurement_id: string;
  source_type: string;
  source_field: string;
  value: number;
  unit: string;
  source_page?: number;
  source_room_id?: string;
  source_text?: string;
}

/**
 * Aufmass item - calculated from measured quantities.
 * Always ground truth with full traceability.
 */
export interface AufmassItem {
  item_id: string;
  position: string;
  description: string;
  quantity: number;
  unit: string;
  derived_from: GroundTruthMeasurement[];
  formula: string;
  formula_description: string;
  unit_price_eur?: number;
  total_price_eur?: number;
  is_ground_truth: true;
}

/**
 * Projected material - estimate with assumptions and confidence.
 * Always clearly labeled as estimate.
 */
export interface ProjectedMaterial {
  material_id: string;
  name: string;
  quantity: number;
  effective_quantity: number;
  unit: string;
  method: ProjectionMethod;
  confidence: number;
  confidence_level: ConfidenceLevel;
  assumptions: string[];
  derived_from_aufmass?: string;
  llm_suggestion?: Record<string, unknown>;
  user_override?: number;
  user_override_reason?: string;
  is_estimate: true;
}

/**
 * Parameters for projection calculation.
 */
export interface ProjectionParams {
  waste_factor?: number;

  // Scaffolding
  scaffold_height_m?: number;
  scaffold_type?: 'standard' | 'rollgeruest' | 'fassade';

  // Drywall
  wall_height_m?: number;
  drywall_system?: 'single' | 'double' | 'fire_rated';
  stud_spacing_mm?: number;

  // Screed
  screed_type?: 'ct' | 'ca' | 'ma';
  screed_thickness_mm?: number;

  // Floor finish
  finish_type?: 'laminate' | 'parquet' | 'tile' | 'carpet';

  // Waterproofing
  waterproofing_type?: 'liquid' | 'membrane' | 'bitumen';
  waterproofing_wall_height_m?: number;
}

/**
 * Request for material projection.
 */
export interface ProjectionRequest {
  extraction_result: Record<string, unknown>;
  trade_type: TradeType;
  params: ProjectionParams;
  use_llm?: boolean;
}

/**
 * Result summary.
 */
export interface ProjectionSummary {
  aufmass_count: number;
  materials_count: number;
  has_errors: boolean;
  has_warnings: boolean;
}

/**
 * Complete projection result.
 */
export interface ProjectionResult {
  projection_id: string;
  trade_type: TradeType;
  trade_name_de: string;
  source_extraction_id: string;
  processed_at: string;
  status: 'ok' | 'partial' | 'error';
  params: ProjectionParams;
  aufmass_items: AufmassItem[];
  projected_materials: ProjectedMaterial[];
  total_aufmass_quantity: number;
  total_estimated_cost_eur?: number;
  errors: string[];
  warnings: string[];
  disclaimer: string;
  summary: ProjectionSummary;
}

/**
 * Trade information from API.
 */
export interface TradeInfo {
  type: TradeType;
  name_de: string;
  name_en: string;
  icon: string;
  required_params: string[];
  optional_params: string[];
  uses_perimeter: boolean;
  uses_area: boolean;
}

// ==================
// API CLIENT
// ==================

const API_BASE = process.env.NEXT_PUBLIC_SNAPGRID_API_URL || 'http://localhost:8000';

/**
 * Get list of available trades.
 */
export async function getAvailableTrades(): Promise<TradeInfo[]> {
  const response = await fetch(`${API_BASE}/api/v1/projections/trades`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch trades' }));
    throw new Error(error.detail || 'Failed to fetch available trades');
  }

  const data = await response.json();
  return data.trades;
}

/**
 * Get detailed information about a specific trade.
 */
export async function getTradeInfo(tradeType: TradeType): Promise<TradeInfo> {
  const response = await fetch(`${API_BASE}/api/v1/projections/trades/${tradeType}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch trade info' }));
    throw new Error(error.detail || `Failed to fetch info for trade: ${tradeType}`);
  }

  return response.json();
}

/**
 * Calculate material projection for a trade.
 */
export async function calculateProjection(
  request: ProjectionRequest
): Promise<ProjectionResult> {
  const response = await fetch(`${API_BASE}/api/v1/projections/calculate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Projection calculation failed' }));
    throw new Error(error.detail || 'Failed to calculate projection');
  }

  return response.json();
}

/**
 * Calculate projections for multiple trades at once.
 */
export async function calculateBatchProjections(
  extractionResult: Record<string, unknown>,
  tradeTypes: TradeType[],
  params?: ProjectionParams
): Promise<Record<TradeType, ProjectionResult | { status: 'error'; error: string }>> {
  const url = new URL(`${API_BASE}/api/v1/projections/calculate/batch`);
  tradeTypes.forEach(t => url.searchParams.append('trade_types', t));

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      extraction_result: extractionResult,
      params: params || {},
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Batch projection failed' }));
    throw new Error(error.detail || 'Failed to calculate batch projections');
  }

  const data = await response.json();
  return data.results;
}

/**
 * Export projection to JSON format.
 */
export async function exportProjectionJson(
  projection: ProjectionResult
): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/v1/projections/export/json`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(projection),
  });

  if (!response.ok) {
    throw new Error('Failed to export projection');
  }

  const data = await response.json();
  return new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
}

// ==================
// UTILITIES
// ==================

/**
 * Trade display information for UI.
 */
export const TRADE_DISPLAY = {
  scaffolding: {
    name: 'Gerüstbau',
    description: 'Facade scaffolding and mobile scaffolds',
    icon: '🏗️',
    color: 'bg-orange-500',
  },
  drywall: {
    name: 'Trockenbau',
    description: 'Gypsum boards, profiles, and fasteners',
    icon: '🧱',
    color: 'bg-gray-500',
  },
  screed: {
    name: 'Estrich',
    description: 'Cement and anhydrite screed',
    icon: '🔲',
    color: 'bg-stone-500',
  },
  floor_finish: {
    name: 'Oberbelag',
    description: 'Laminate, parquet, tile, carpet',
    icon: '🏠',
    color: 'bg-amber-500',
  },
  waterproofing: {
    name: 'Abdichtung',
    description: 'Waterproofing for wet rooms',
    icon: '💧',
    color: 'bg-blue-500',
  },
} as const;

/**
 * Get confidence badge color based on level.
 */
export function getConfidenceColor(level: ConfidenceLevel): string {
  switch (level) {
    case 'high':
      return 'bg-green-500/20 text-green-400 border-green-500/30';
    case 'medium':
      return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
    case 'low':
      return 'bg-red-500/20 text-red-400 border-red-500/30';
    default:
      return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
  }
}

/**
 * Get confidence badge label.
 */
export function getConfidenceLabel(level: ConfidenceLevel): string {
  switch (level) {
    case 'high':
      return 'Hoch';
    case 'medium':
      return 'Mittel';
    case 'low':
      return 'Niedrig';
    default:
      return 'Unbekannt';
  }
}

/**
 * Format number with German locale.
 */
export function formatQuantity(value: number, decimals: number = 2): string {
  return value.toLocaleString('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Download blob as file.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ==================
// DRYWALL SYMBOL DETECTION (Plankopf-based)
// ==================

/**
 * Legend symbol from Plankopf parsing.
 */
export interface LegendSymbol {
  symbol_id: string;
  label: string;
  label_normalized: string;
  material_type: string | null;
  pattern_info: {
    pattern_type: string;
    stroke_color: number[] | null;
    fill_color: number[] | null;
    hatching_angle: number | null;
    hatching_spacing: number | null;
    line_count: number;
  };
  confidence: number;
}

/**
 * Detected drywall segment.
 */
export interface DrywallSegment {
  segment_id: string;
  bbox: { x0: number; y0: number; x1: number; y1: number };
  length_m: number;
  area_m2: number;
  wall_height_m: number;
  confidence: number;
  page_number: number;
}

/**
 * Detection result for a single drywall type.
 */
export interface DrywallResultItem {
  detection_id: string;
  material_label: string;
  material_type: string;
  segments: DrywallSegment[];
  total_count: number;
  total_length_m: number;
  total_area_m2: number;
  wall_height_m: number;
  scale: string;
  confidence: number;
  pages_analyzed: number[];
  assumptions: string[];
  warnings: string[];
}

/**
 * Full drywall detection response from Plankopf-based analysis.
 */
export interface DrywallDetectionResult {
  extraction_id: string;
  filename: string;
  page_count: number;
  status: 'ok' | 'partial' | 'error';

  // Plankopf info
  plankopf_found: boolean;
  plankopf_page: number | null;
  legend_symbols: LegendSymbol[];

  // Detection results
  drywall_results: DrywallResultItem[];

  // Totals
  grand_total_length_m: number;
  grand_total_area_m2: number;
  grand_total_segments: number;

  // Settings
  scale: string;
  wall_height_m: number;

  // Metadata
  processed_at: string;
  errors: string[];
  warnings: string[];
}

/**
 * Detect drywall using Plankopf symbol matching.
 * This reads the legend/title block to learn what patterns represent drywall,
 * then scans the drawing for matching patterns.
 */
export async function detectDrywallFromSymbols(
  file: File,
  options?: {
    wall_height_m?: number;
    target_label?: string;
    scale?: string;
    page_numbers?: number[];
  }
): Promise<DrywallDetectionResult> {
  const formData = new FormData();
  formData.append('file', file);

  const params = new URLSearchParams();
  if (options?.wall_height_m) {
    params.append('wall_height_m', options.wall_height_m.toString());
  }
  if (options?.target_label) {
    params.append('target_label', options.target_label);
  }
  if (options?.scale) {
    params.append('scale', options.scale);
  }
  if (options?.page_numbers && options.page_numbers.length > 0) {
    params.append('page_numbers', options.page_numbers.join(','));
  }

  const url = `${API_BASE}/api/v1/drywall-detection/from-symbols${params.toString() ? '?' + params.toString() : ''}`;
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Detection failed' }));
    throw new Error(error.detail || 'Failed to detect drywall from symbols');
  }

  return response.json();
}

/**
 * Analyze only the Plankopf/legend without full detection.
 * Use this to preview what symbols are available.
 */
export async function analyzePlankopfLegend(
  file: File,
  pageNumber: number = 0
): Promise<{
  plankopf_found: boolean;
  page_number: number;
  symbols: LegendSymbol[];
  drywall_symbols: LegendSymbol[];
  warnings: string[];
}> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(
    `${API_BASE}/api/v1/drywall-detection/analyze-legend?page_number=${pageNumber}`,
    {
      method: 'POST',
      body: formData,
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Legend analysis failed' }));
    throw new Error(error.detail || 'Failed to analyze legend');
  }

  return response.json();
}
