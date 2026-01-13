/**
 * Artifact Studio API Client
 *
 * Connects to the FastAPI backend for generating and managing
 * interactive construction detail sketches.
 */

const API_BASE = process.env.NEXT_PUBLIC_SNAPGRID_API_URL || 'http://localhost:8000';

// =============================================================================
// Types
// =============================================================================

export type ArtifactType = 'interactive' | 'svg' | 'mermaid' | 'html';

export interface ArtifactContext {
  project?: string;
  floor?: string;
  grid_axis?: string;
  wall_id?: string;
  detail_type?: string;
}

export interface GenerateRequest {
  prompt: string;
  trade_preset?: string;
  context?: ArtifactContext;
}

export interface Artifact {
  artifact_id: string;
  title: string;
  type: ArtifactType;
  summary: string;
  bullet_points: string[];
  code: string;
  assets?: Record<string, unknown>;
  created_at: string;
  input_prompt: string;
  trade_preset?: string;
  context?: Record<string, string>;
  version_number: number;
  parent_id?: string;
}

export interface GenerateResponse {
  success: boolean;
  artifact?: Artifact;
  error?: string;
  tokens_used: number;
  model: string;
}

export interface ArtifactListResponse {
  artifacts: Artifact[];
  total_count: number;
}

export interface PromptTemplate {
  id: string;
  name_de: string;
  name_en: string;
  prompt: string;
  trade: string;
  interactive?: boolean;
}

export interface TemplateListResponse {
  templates: PromptTemplate[];
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Generate a new artifact using Claude AI.
 */
export async function generateArtifact(request: GenerateRequest): Promise<GenerateResponse> {
  const response = await fetch(`${API_BASE}/api/v1/artifacts/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Generation failed' }));
    throw new Error(error.detail || 'Failed to generate artifact');
  }

  return response.json();
}

/**
 * List all saved artifacts.
 */
export async function listArtifacts(
  limit: number = 50,
  offset: number = 0
): Promise<ArtifactListResponse> {
  const response = await fetch(
    `${API_BASE}/api/v1/artifacts/list?limit=${limit}&offset=${offset}`
  );

  if (!response.ok) {
    throw new Error('Failed to list artifacts');
  }

  return response.json();
}

/**
 * Get a specific artifact by ID.
 */
export async function getArtifact(artifactId: string): Promise<Artifact> {
  const response = await fetch(`${API_BASE}/api/v1/artifacts/${artifactId}`);

  if (!response.ok) {
    throw new Error('Artifact not found');
  }

  return response.json();
}

/**
 * Delete an artifact by ID.
 */
export async function deleteArtifact(artifactId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/artifacts/${artifactId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error('Failed to delete artifact');
  }
}

/**
 * Create a new version of an existing artifact.
 */
export async function createVersion(
  parentId: string,
  request: GenerateRequest
): Promise<GenerateResponse> {
  const response = await fetch(`${API_BASE}/api/v1/artifacts/${parentId}/version`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Version creation failed' }));
    throw new Error(error.detail || 'Failed to create version');
  }

  return response.json();
}

/**
 * Get available prompt templates.
 */
export async function getTemplates(): Promise<TemplateListResponse> {
  const response = await fetch(`${API_BASE}/api/v1/artifacts/templates/list`);

  if (!response.ok) {
    throw new Error('Failed to load templates');
  }

  return response.json();
}

/**
 * Check artifact service health.
 */
export async function checkArtifactHealth(): Promise<{
  status: string;
  service: string;
  anthropic_enabled: boolean;
}> {
  const response = await fetch(`${API_BASE}/api/v1/artifacts/health`);

  if (!response.ok) {
    throw new Error('Health check failed');
  }

  return response.json();
}
