"""
Artifact Generation Service

Uses Anthropic Claude API to generate interactive construction detail sketches.
Outputs structured JSON with type (interactive/svg/mermaid/html), code, and component data.

SECURITY: All HTML output is sanitized to remove scripts and event handlers.
Interactive mode generates structured data for a pre-built viewer component.
"""

import json
import json5  # Lenient JSON parser for LLM output
import logging
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from ..core.config import settings

logger = logging.getLogger(__name__)


class ArtifactType(str, Enum):
    """Supported artifact output types."""
    INTERACTIVE = "interactive"  # Rich interactive viewer with sound effects
    SVG = "svg"
    MERMAID = "mermaid"
    HTML = "html"


@dataclass
class ArtifactOutput:
    """Generated artifact structure."""
    title: str
    type: ArtifactType
    summary: str
    bullet_points: List[str]
    code: str
    assets: Optional[Dict[str, Any]] = None


@dataclass
class GenerationResult:
    """Result of artifact generation."""
    success: bool
    artifact: Optional[ArtifactOutput]
    error: Optional[str] = None
    tokens_used: int = 0
    model: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "artifact": {
                "title": self.artifact.title,
                "type": self.artifact.type.value,
                "summary": self.artifact.summary,
                "bullet_points": self.artifact.bullet_points,
                "code": self.artifact.code,
                "assets": self.artifact.assets,
            } if self.artifact else None,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "model": self.model,
        }


def get_anthropic_client():
    """Get Anthropic client with API key from settings."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    if not settings.anthropic_api_key:
        raise ValueError("SNAPGRID_ANTHROPIC_API_KEY not set in environment")

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


# System prompt for INTERACTIVE construction detail generation
INTERACTIVE_SYSTEM_PROMPT = """You generate INTERACTIVE construction detail JSON for German professionals.

RESPOND WITH VALID JSON ONLY - NO MARKDOWN, NO COMMENTS.

JSON STRUCTURE:
{
  "title": "German title",
  "type": "interactive",
  "summary": "2 sentences in German",
  "bullet_points": ["Point 1", "Point 2", "Point 3"],
  "data": {
    "components": {
      "component-id": {
        "name": "German name",
        "shortName": "Code",
        "din": "DIN number",
        "category": ["load-bearing"],
        "material": {"description": "Material", "composition": "Details", "dimensions": "Size"},
        "function": "What it does (German)",
        "failureModes": [{"type": "Name", "severity": "high", "description": "Issue"}],
        "installation": ["Step 1", "Step 2"],
        "acoustic": {"rating": "dB value", "notes": "Notes"},
        "fire": {"rating": "F30/F60/F90", "notes": "Notes"}
      }
    },
    "layerCategories": [
      {"id": "all", "name": "Alle", "color": "#6B7280"},
      {"id": "load-bearing", "name": "Tragwerk", "color": "#1E3A5F"},
      {"id": "finishing", "name": "Bekleidung", "color": "#8B7355"},
      {"id": "acoustic", "name": "Akustik", "color": "#4A6741"}
    ],
    "failureScenarios": [
      {"id": "scenario-1", "name": "Name", "description": "What fails", "affectedComponents": ["component-id"], "severity": "critical"}
    ],
    "svgContent": "<svg>...</svg>",
    "dimensions": {"width": 500, "height": 400}
  }
}

SVG RULES:
1. Use viewBox="0 0 500 400"
2. Wrap each clickable part in <g id="component-id" style="cursor:pointer">
3. The g id MUST match a key in components object
4. Keep SVG simple - use basic shapes (rect, path, line)
5. Use these colors: Concrete #C0C0C0, Gypsum #F5F0E6, Insulation #8FBC8F, Steel #B0B0B0

IMPORTANT:
- Include exactly 4-5 components (not more)
- Keep descriptions short (1-2 sentences max)
- All text in German
- Valid JSON only - check your commas!
"""

# Legacy system prompt for simple SVG/Mermaid/HTML
SIMPLE_SYSTEM_PROMPT = """You are a construction detail sketch generator for German construction documents (Baudetails).

You create visual diagrams and sketches for:
- Wall-to-floor junctions (Boden-Wand-Anschluss)
- Door frame details (Türzargendetail)
- Firestopping details (Brandschutzabschottung)
- Drywall specifications (Trockenbaudetail)
- Electrical routing (Elektroinstallation)
- Insulation details (Dämmungsdetail)

ALWAYS respond with valid JSON in this exact format:
{
  "title": "Brief descriptive title in German",
  "type": "svg" | "mermaid" | "html",
  "summary": "2-3 sentence explanation of the detail in German",
  "bullet_points": ["Key point 1", "Key point 2", "Key point 3"],
  "code": "The SVG/Mermaid/HTML code",
  "assets": {"notes": "Optional additional notes"}
}

IMPORTANT RULES:
1. PREFER SVG for all visual diagrams - they are scalable and portable
2. Use Mermaid for flowcharts, decision trees, sequences, and hierarchical diagrams
3. Use HTML only for tables, schedules, or text-heavy content
4. NEVER output "react" type - always use SVG or HTML instead
5. All dimensions should use metric units (mm, cm, m)
6. Include German labels (with optional English in parentheses)
7. Use construction-standard colors:
   - Concrete/Beton: #C0C0C0
   - Drywall/Gipskarton: #F5F5DC
   - Insulation/Dämmung: #FFE4B5
   - Steel/Stahl: #708090
   - Wood/Holz: #DEB887
   - Waterproofing/Abdichtung: #4A90D9

For SVG output:
- Use viewBox="0 0 400 300" for responsive sizing
- Include proper stroke widths for printing (strokeWidth 1-2)
- Add hatching patterns for materials where appropriate
- Label all dimensions with text elements
- Use clean, professional line work

For Mermaid output:
- Use flowchart TD for vertical flows
- Use graph LR for horizontal processes
- Include clear node labels in German

For HTML output:
- Use simple table structures
- Include proper headers
- Keep styling inline and minimal
"""


def repair_json(json_str: str) -> str:
    """
    Attempt to repair common JSON syntax errors from LLM output.

    Common issues:
    - Missing commas between properties
    - Trailing commas
    - Unescaped special characters in strings
    """
    # Remove any markdown code block markers
    json_str = re.sub(r'^```json?\s*', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'\s*```$', '', json_str, flags=re.MULTILINE)

    # Fix trailing commas before closing brackets/braces
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

    # Try to fix missing commas between properties
    # Pattern: "value"\n"key" should be "value",\n"key"
    json_str = re.sub(r'"\s*\n(\s*)"', '",\n\\1"', json_str)

    # Pattern: }\n{ or ]\n{ should have comma
    json_str = re.sub(r'(\})\s*\n(\s*\{)', r'\1,\n\2', json_str)
    json_str = re.sub(r'(\])\s*\n(\s*\{)', r'\1,\n\2', json_str)

    # Pattern: }\n" should be },\n"
    json_str = re.sub(r'(\})\s*\n(\s*")', r'\1,\n\2', json_str)
    json_str = re.sub(r'(\])\s*\n(\s*")', r'\1,\n\2', json_str)

    # Fix numbers followed by " without comma
    json_str = re.sub(r'(\d)\s*\n(\s*")', r'\1,\n\2', json_str)

    # Fix true/false/null followed by " without comma
    json_str = re.sub(r'(true|false|null)\s*\n(\s*")', r'\1,\n\2', json_str, flags=re.IGNORECASE)

    return json_str


def sanitize_html(html: str) -> str:
    """
    Remove potentially dangerous elements from HTML/SVG output.

    Security measures:
    - Remove script tags with their content
    - Remove on* event handlers (onclick, onerror, etc.)
    - Remove javascript: URLs
    - Remove data: URLs (potential XSS vector)
    - Remove style expressions
    """
    # Remove script tags (with content)
    html = re.sub(
        r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>',
        '',
        html,
        flags=re.IGNORECASE
    )

    # Remove on* event handlers (various formats)
    html = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', html, flags=re.IGNORECASE)
    html = re.sub(r'\s+on\w+\s*=\s*[^\s>]+', '', html, flags=re.IGNORECASE)

    # Remove javascript: URLs
    html = re.sub(r'javascript:', '', html, flags=re.IGNORECASE)

    # Remove data: URLs (can be XSS vectors)
    html = re.sub(r'href\s*=\s*["\']data:', 'href="', html, flags=re.IGNORECASE)

    # Remove style expressions (IE-specific but good to block)
    html = re.sub(r'expression\s*\(', '', html, flags=re.IGNORECASE)

    # Remove vbscript: URLs
    html = re.sub(r'vbscript:', '', html, flags=re.IGNORECASE)

    return html


def generate_artifact(
    prompt: str,
    trade_preset: Optional[str] = None,
    context: Optional[Dict[str, str]] = None,
    retry_count: int = 2,
    interactive_mode: bool = True,  # Default to interactive mode
) -> GenerationResult:
    """
    Generate an artifact using Claude.

    Args:
        prompt: User's natural language prompt describing the desired sketch
        trade_preset: Optional trade type (flooring, drywall, electrical, insulation, doors)
        context: Optional context fields (project, floor, grid_axis, wall_id, detail_type)
        retry_count: Number of retries on invalid JSON response
        interactive_mode: If True, generate rich interactive data; if False, generate simple SVG/HTML

    Returns:
        GenerationResult with generated artifact or error details
    """
    try:
        client = get_anthropic_client()
    except Exception as e:
        logger.error(f"Failed to initialize Anthropic client: {e}")
        return GenerationResult(success=False, artifact=None, error=str(e))

    # Build context-aware prompt
    full_prompt = prompt

    # Add trade context
    trade_labels = {
        "flooring": "Oberbelag/Bodenbelag",
        "drywall": "Trockenbau",
        "electrical": "Elektroinstallation",
        "insulation": "Dämmung",
        "doors": "Türen/Zargen",
    }
    if trade_preset and trade_preset in trade_labels:
        full_prompt = f"[Gewerk: {trade_labels[trade_preset]}]\n\n{full_prompt}"

    # Add context fields
    if context:
        context_parts = []
        context_labels = {
            "project": "Projekt",
            "floor": "Geschoss",
            "grid_axis": "Achse/Raster",
            "wall_id": "Wand-ID",
            "detail_type": "Detailtyp",
        }
        for key, value in context.items():
            if value:
                label = context_labels.get(key, key)
                context_parts.append(f"{label}: {value}")

        if context_parts:
            full_prompt = f"[Kontext: {', '.join(context_parts)}]\n\n{full_prompt}"

    # Choose system prompt based on mode
    system_prompt = INTERACTIVE_SYSTEM_PROMPT if interactive_mode else SIMPLE_SYSTEM_PROMPT

    # Attempt generation with retries
    for attempt in range(retry_count + 1):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=16000,  # Large buffer to prevent truncation
                system=system_prompt,
                messages=[
                    {"role": "user", "content": full_prompt}
                ],
            )

            content = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            # Parse JSON response
            try:
                # Try to extract JSON from the response (may have markdown wrapping)
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    json_str = json_match.group()
                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Standard JSON parse failed: {e}")
                        # Try to repair the JSON first
                        logger.warning("Attempting JSON repair...")
                        repaired = repair_json(json_str)
                        try:
                            data = json.loads(repaired)
                        except json.JSONDecodeError:
                            # Use json5 as final fallback (more lenient parser)
                            logger.warning("Using json5 lenient parser...")
                            data = json5.loads(repaired)
                else:
                    raise ValueError("No JSON object found in response")

                # Validate required fields
                required_fields = ["title", "type", "summary", "bullet_points"]
                for field in required_fields:
                    if field not in data:
                        raise ValueError(f"Missing required field: {field}")

                # Validate and normalize type
                art_type = data["type"].lower()

                # Handle interactive type
                if art_type == "interactive":
                    if "data" not in data:
                        raise ValueError("Interactive type requires 'data' field")

                    # Store the entire data structure as code (JSON string)
                    code = json.dumps(data["data"], ensure_ascii=False)

                    # Sanitize any SVG content within the data
                    if "svgContent" in data["data"]:
                        data["data"]["svgContent"] = sanitize_html(data["data"]["svgContent"])
                        code = json.dumps(data["data"], ensure_ascii=False)

                    artifact = ArtifactOutput(
                        title=data["title"],
                        type=ArtifactType.INTERACTIVE,
                        summary=data["summary"],
                        bullet_points=data["bullet_points"] if isinstance(data["bullet_points"], list) else [data["bullet_points"]],
                        code=code,
                        assets=data.get("assets"),
                    )

                    return GenerationResult(
                        success=True,
                        artifact=artifact,
                        tokens_used=tokens_used,
                        model="claude-sonnet-4-5-20250929",
                    )

                # Handle legacy types
                if art_type == "react":
                    # Convert react to html with warning
                    art_type = "html"
                    data["assets"] = data.get("assets", {})
                    data["assets"]["notes"] = "Converted from React to static HTML for security"
                    logger.warning("Converted 'react' artifact type to 'html' for security")

                if art_type not in ["svg", "mermaid", "html"]:
                    raise ValueError(f"Invalid artifact type: {art_type}. Must be interactive, svg, mermaid, or html.")

                if "code" not in data:
                    raise ValueError("Missing required field: code")

                # Sanitize code output
                code = data["code"]
                if art_type in ["html", "svg"]:
                    code = sanitize_html(code)

                # Build artifact output
                artifact = ArtifactOutput(
                    title=data["title"],
                    type=ArtifactType(art_type),
                    summary=data["summary"],
                    bullet_points=data["bullet_points"] if isinstance(data["bullet_points"], list) else [data["bullet_points"]],
                    code=code,
                    assets=data.get("assets"),
                )

                return GenerationResult(
                    success=True,
                    artifact=artifact,
                    tokens_used=tokens_used,
                    model="claude-sonnet-4-5-20250929",
                )

            except (json.JSONDecodeError, ValueError) as e:
                if attempt < retry_count:
                    logger.warning(f"Invalid response format (attempt {attempt + 1}): {e}. Retrying...")
                    continue

                logger.error(f"Failed to parse artifact response: {e}")
                return GenerationResult(
                    success=False,
                    artifact=None,
                    error=f"Invalid response format: {str(e)}",
                    tokens_used=tokens_used,
                    model="claude-sonnet-4-5-20250929",
                )

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return GenerationResult(
                success=False,
                artifact=None,
                error=str(e),
            )

    return GenerationResult(
        success=False,
        artifact=None,
        error="Max retries exceeded without valid response",
    )


# Prompt templates for quick access - now with interactive flag
PROMPT_TEMPLATES = [
    {
        "id": "wall_floor_junction",
        "name_de": "Boden-Wand-Anschluss (Interaktiv)",
        "name_en": "Wall-Floor Junction (Interactive)",
        "prompt": "Erstelle ein interaktives Detail für den Anschluss zwischen Trockenbauwand und Doppelboden. Zeige UW-Profile, CW-Ständer, Gipskartonbeplankung, Mineralwolle-Dämmung, Trennstreifen und Doppelboden-Elemente. Inkludiere alle relevanten DIN-Normen und typische Fehlerquellen.",
        "trade": "flooring",
        "interactive": True,
    },
    {
        "id": "door_schedule_diagram",
        "name_de": "Türenlisten-Diagramm",
        "name_en": "Door Schedule Diagram",
        "prompt": "Erstelle ein Flussdiagramm für die Türkategorien: Standard, T30-RS (Rauchschutz), T90 (Brandschutz), DSS (Schallschutz). Zeige Entscheidungskriterien und typische Einbauorte.",
        "trade": "doors",
        "interactive": False,
    },
    {
        "id": "firestopping_detail",
        "name_de": "Brandschutzabschottung (Interaktiv)",
        "name_en": "Firestopping Detail (Interactive)",
        "prompt": "Erstelle ein interaktives Detail einer Brandschutzabschottung für Kabeltrassen durch eine F90 Wand. Zeige Brandschutzmanschette, Brandschutzmörtel, Mineralwolle und alle beteiligten Komponenten mit DIN-Normen und Fehlerquellen.",
        "trade": "electrical",
        "interactive": True,
    },
    {
        "id": "drywall_system",
        "name_de": "Trockenbausystem (Interaktiv)",
        "name_en": "Drywall System (Interactive)",
        "prompt": "Erstelle ein interaktives Detail einer CW75 Ständerwand mit doppelter Gipskartonbeplankung (2x12,5mm GKB), UW-Profilen, Mineralwolle-Füllung, Trennstreifen und Fugendichtung. Zeige alle Komponenten mit DIN-Normen, Materialspezifikationen und typischen Fehlern.",
        "trade": "drywall",
        "interactive": True,
    },
    {
        "id": "electrical_routing",
        "name_de": "Elektro-Leitungsführung",
        "name_en": "Electrical Routing",
        "prompt": "Zeige die normgerechte Leitungsführung in einer Büroeinheit mit Installationszonen nach DIN 18015. Markiere Schalterhöhen, Steckdosenzonen und Verteilerwege.",
        "trade": "electrical",
        "interactive": False,
    },
]


def get_prompt_templates() -> List[Dict[str, str]]:
    """Get available prompt templates."""
    return PROMPT_TEMPLATES
