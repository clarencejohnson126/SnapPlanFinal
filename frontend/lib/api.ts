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
  return response.json();
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
export function formatNumber(num: number, decimals: number = 2): string {
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
