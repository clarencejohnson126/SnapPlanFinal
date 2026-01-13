/**
 * SnapPlan API Service
 * Connects frontend to FastAPI backend
 */

const API_BASE = process.env.NEXT_PUBLIC_SNAPGRID_API_URL || 'http://localhost:8000';

export interface ExtractedRoom {
  room_number: string;
  room_name: string;
  area_m2: number;
  counted_m2: number;
  factor: number;
  page: number;
  source_text: string;
  category: string;
  extraction_pattern: string;
  perimeter_m?: number;
  height_m?: number;
  bbox?: {
    x0: number;
    y0: number;
    x1: number;
    y1: number;
  };
}

export interface RevisionCloud {
  page: number;
  bbox: { x0: number; y0: number; x1: number; y1: number };
  color: { r: number; g: number; b: number };
  confidence: number;
  arc_count: number;
  associated_text?: string;
  affected_room_numbers: string[];
}

export interface RevisionCloudSummary {
  clouds: RevisionCloud[];
  total_count: number;
  pages_with_clouds: number[];
  warning_message: string;
}

export interface ExtractionResult {
  rooms: ExtractedRoom[];
  total_area_m2: number;
  total_counted_m2: number;
  room_count: number;
  page_count: number;
  blueprint_style: string;
  extraction_method: string;
  warnings: string[];
  totals_by_category: Record<string, number>;
  revision_clouds?: RevisionCloudSummary;
}

export interface InterpretationResult {
  success: boolean;
  interpretation_type: string;
  content: string;
  language: string;
  tokens_used: number;
  model: string;
  error?: string;
}

export interface ExtractionWithInterpretation {
  extraction: ExtractionResult;
  interpretation?: InterpretationResult;
  quick_summary?: string;
}

// Health check
export async function checkHealth(): Promise<{ status: string; version: string }> {
  const response = await fetch(`${API_BASE}/api/v1/extraction/health`);
  if (!response.ok) throw new Error('Health check failed');
  return response.json();
}

// Detect blueprint style
export async function detectStyle(file: File): Promise<{ style: string; confidence: number }> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}/api/v1/extraction/detect-style`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) throw new Error('Style detection failed');
  return response.json();
}

// Backend response structure (nested)
interface BackendExtractionResponse {
  extraction_id: string;
  source_file: string;
  extracted_at: string;
  summary: {
    total_rooms: number;
    total_area_m2: number;
    total_counted_m2: number;
    blueprint_style: string;
    page_count: number;
    by_category: Array<{ category: string; area_m2: number; room_count: number }>;
  };
  rooms: ExtractedRoom[];
  warnings: string[];
  revision_clouds?: RevisionCloudSummary;
}

// Extract rooms from PDF
export async function extractRooms(
  file: File,
  style?: string,
  pages?: number[]
): Promise<ExtractionResult> {
  const formData = new FormData();
  formData.append('file', file);

  let url = `${API_BASE}/api/v1/extraction/rooms`;
  const params = new URLSearchParams();
  if (style) params.append('style', style);
  if (pages) params.append('pages', pages.join(','));
  const paramString = params.toString();
  if (paramString) url += `?${paramString}`;

  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Extraction failed');
  }

  // Transform backend response to frontend format
  const backendData: BackendExtractionResponse = await response.json();

  // Convert by_category array to totals_by_category object
  const totals_by_category: Record<string, number> = {};
  for (const cat of backendData.summary.by_category) {
    totals_by_category[cat.category] = cat.area_m2;
  }

  return {
    rooms: backendData.rooms,
    total_area_m2: backendData.summary.total_area_m2,
    total_counted_m2: backendData.summary.total_counted_m2,
    room_count: backendData.summary.total_rooms,
    page_count: backendData.summary.page_count,
    blueprint_style: backendData.summary.blueprint_style,
    extraction_method: 'text_pattern',
    warnings: backendData.warnings,
    totals_by_category,
    revision_clouds: backendData.revision_clouds,
  };
}

// Extract rooms with AI interpretation
export async function extractAndInterpret(
  file: File,
  interpretationType: string = 'summary',
  language: string = 'de'
): Promise<ExtractionWithInterpretation> {
  const formData = new FormData();
  formData.append('file', file);

  const url = `${API_BASE}/api/v1/extraction/extract-and-interpret?interpretation_type=${interpretationType}&language=${language}`;

  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Extraction failed');
  }
  return response.json();
}

// Get quick summary (no LLM)
export async function getQuickSummary(
  extractionData: ExtractionResult,
  language: string = 'de'
): Promise<{ summary: string }> {
  const response = await fetch(`${API_BASE}/api/v1/extraction/quick-summary?language=${language}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(extractionData),
  });

  if (!response.ok) throw new Error('Summary generation failed');
  return response.json();
}

// Export to Excel
export async function exportToExcel(
  extractionData: ExtractionResult,
  projectName: string = 'SnapPlan Export'
): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/v1/extraction/export/excel?project_name=${encodeURIComponent(projectName)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(extractionData),
  });

  if (!response.ok) throw new Error('Export failed');
  return response.blob();
}

// Export to CSV
export async function exportToCSV(extractionData: ExtractionResult): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/v1/extraction/export/csv`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(extractionData),
  });

  if (!response.ok) throw new Error('Export failed');
  return response.blob();
}

// Export to PDF
export async function exportToPDF(
  extractionData: ExtractionResult,
  projectName: string = 'SnapPlan Export'
): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/v1/extraction/export/pdf?project_name=${encodeURIComponent(projectName)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(extractionData),
  });

  if (!response.ok) throw new Error('PDF Export failed');
  return response.blob();
}

// Client-side CSV export (fallback when backend unavailable)
export function generateCSV(extractionData: ExtractionResult): Blob {
  const headers = ['Room Number', 'Room Name', 'Area (m²)', 'Counted (m²)', 'Factor', 'Category', 'Page'];
  const rows = extractionData.rooms.map(room => [
    room.room_number,
    room.room_name,
    room.area_m2.toFixed(2),
    room.counted_m2.toFixed(2),
    room.factor.toString(),
    room.category,
    room.page.toString(),
  ]);

  const csvContent = [headers.join(','), ...rows.map(row => row.map(cell => `"${cell}"`).join(','))].join('\n');
  return new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
}

// Get room categories
export async function getRoomCategories(): Promise<{ categories: string[] }> {
  const response = await fetch(`${API_BASE}/api/v1/extraction/categories`);
  if (!response.ok) throw new Error('Failed to get categories');
  return response.json();
}

// Get AI interpretation
export async function getInterpretation(
  extractionData: ExtractionResult,
  interpretationType: string = 'summary',
  language: string = 'de'
): Promise<InterpretationResult> {
  const response = await fetch(
    `${API_BASE}/api/v1/extraction/interpret?interpretation_type=${interpretationType}&language=${language}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(extractionData),
    }
  );

  if (!response.ok) throw new Error('Interpretation failed');
  return response.json();
}

// Format number for display (German format)
export function formatNumber(num: number | undefined | null, decimals: number = 2): string {
  if (num === undefined || num === null || isNaN(num)) {
    return '0,00';
  }
  return num.toLocaleString('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

// Format area with unit
export function formatArea(area: number): string {
  return `${formatNumber(area)} m²`;
}

// Get category display name
export function getCategoryDisplayName(category: string, language: string = 'de'): string {
  const names: Record<string, Record<string, string>> = {
    de: {
      office: 'Büro',
      residential: 'Wohnen',
      circulation: 'Verkehrsfläche',
      stairs: 'Treppen',
      elevators: 'Aufzüge',
      shafts: 'Schächte',
      technical: 'Technik',
      sanitary: 'Sanitär',
      storage: 'Lager',
      outdoor: 'Außenfläche',
      other: 'Sonstige',
    },
    en: {
      office: 'Office',
      residential: 'Residential',
      circulation: 'Circulation',
      stairs: 'Stairs',
      elevators: 'Elevators',
      shafts: 'Shafts',
      technical: 'Technical',
      sanitary: 'Sanitary',
      storage: 'Storage',
      outdoor: 'Outdoor',
      other: 'Other',
    },
  };

  return names[language]?.[category] || names['en']?.[category] || category;
}

// Get style display name
export function getStyleDisplayName(style: string, language: string = 'de'): string {
  const names: Record<string, Record<string, string>> = {
    de: {
      haardtring: 'Wohngebäude (Haardtring)',
      leiq: 'Bürogebäude (LeiQ)',
      omniturm: 'Hochhaus (Omniturm)',
      unknown: 'Unbekannt',
    },
    en: {
      haardtring: 'Residential (Haardtring)',
      leiq: 'Office (LeiQ)',
      omniturm: 'Highrise (Omniturm)',
      unknown: 'Unknown',
    },
  };

  return names[language]?.[style] || names['en']?.[style] || style;
}
