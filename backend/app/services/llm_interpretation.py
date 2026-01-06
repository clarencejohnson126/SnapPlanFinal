"""
LLM Interpretation Service

Uses OpenAI API to interpret extraction results and generate:
- Natural language summaries
- Smart tips for construction professionals
- Cost estimates
- Comparisons and insights

IMPORTANT: This service ONLY interprets already-extracted data.
It does NOT extract values from PDFs - all numbers come from deterministic extraction.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class InterpretationType(str, Enum):
    """Type of interpretation to generate."""
    SUMMARY = "summary"
    SMART_TIPS = "smart_tips"
    COST_ESTIMATE = "cost_estimate"
    COMPARISON = "comparison"
    FULL_REPORT = "full_report"


@dataclass
class InterpretationResult:
    """Result of LLM interpretation."""
    success: bool
    interpretation_type: InterpretationType
    content: str
    language: str
    tokens_used: int
    model: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "interpretation_type": self.interpretation_type.value,
            "content": self.content,
            "language": self.language,
            "tokens_used": self.tokens_used,
            "model": self.model,
            "error": self.error,
        }


def get_openai_client():
    """Get OpenAI client with API key from environment."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")

    return OpenAI(api_key=api_key)


def interpret_extraction(
    extraction_data: Dict[str, Any],
    interpretation_type: InterpretationType = InterpretationType.SUMMARY,
    language: str = "de",
    custom_prompt: Optional[str] = None,
) -> InterpretationResult:
    """
    Interpret extraction results using OpenAI.

    Args:
        extraction_data: Dictionary with extraction results (rooms, totals, etc.)
        interpretation_type: Type of interpretation to generate
        language: Output language (de=German, en=English)
        custom_prompt: Optional custom prompt to override default

    Returns:
        InterpretationResult with generated content
    """
    try:
        client = get_openai_client()
    except Exception as e:
        return InterpretationResult(
            success=False,
            interpretation_type=interpretation_type,
            content="",
            language=language,
            tokens_used=0,
            model="none",
            error=str(e),
        )

    # Build system prompt based on interpretation type
    system_prompt = _build_system_prompt(interpretation_type, language)

    # Build user prompt with extraction data
    if custom_prompt:
        user_prompt = custom_prompt + "\n\nData:\n" + json.dumps(extraction_data, indent=2, ensure_ascii=False)
    else:
        user_prompt = _build_user_prompt(extraction_data, interpretation_type, language)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        content = response.choices[0].message.content
        tokens_used = response.usage.total_tokens if response.usage else 0

        return InterpretationResult(
            success=True,
            interpretation_type=interpretation_type,
            content=content,
            language=language,
            tokens_used=tokens_used,
            model="gpt-4o-mini",
        )

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return InterpretationResult(
            success=False,
            interpretation_type=interpretation_type,
            content="",
            language=language,
            tokens_used=0,
            model="gpt-4o-mini",
            error=str(e),
        )


def _build_system_prompt(interpretation_type: InterpretationType, language: str) -> str:
    """Build system prompt based on interpretation type."""

    base_context = """Du bist ein Experte für Bauplanung und Aufmaßerstellung in Deutschland.
Du analysierst extrahierte Raumdaten aus PDF-Grundrissen und gibst hilfreiche Zusammenfassungen.

WICHTIG: Du generierst KEINE Zahlen. Alle m²-Werte stammen aus der deterministischen Extraktion.
Du interpretierst und erklärst nur die bereits extrahierten Daten."""

    if language == "en":
        base_context = """You are an expert in German construction planning and measurement take-offs (Aufmaß).
You analyze extracted room data from PDF floor plans and provide helpful summaries.

IMPORTANT: You do NOT generate numbers. All m² values come from deterministic extraction.
You only interpret and explain the already-extracted data."""

    type_prompts = {
        InterpretationType.SUMMARY: """Erstelle eine übersichtliche Zusammenfassung der extrahierten Raumdaten.
Gruppiere nach Kategorien und hebe wichtige Kennzahlen hervor.""" if language == "de" else
"""Create a clear summary of the extracted room data.
Group by categories and highlight key metrics.""",

        InterpretationType.SMART_TIPS: """Gib praktische Tipps für Bauleiter und Handwerker basierend auf den Daten:
- Hinweise zur Materialbestellung
- Potenzielle Problembereiche
- Optimierungsmöglichkeiten
- Zeitplanung-Tipps""" if language == "de" else
"""Provide practical tips for construction managers and craftsmen based on the data:
- Material ordering hints
- Potential problem areas
- Optimization opportunities
- Scheduling tips""",

        InterpretationType.COST_ESTIMATE: """Erstelle eine grobe Kostenschätzung basierend auf den m²-Werten.
Verwende typische deutsche Marktpreise (2024):
- Bodenbelag: 30-80 €/m²
- Malerarbeiten: 15-35 €/m²
- Trockenbau: 40-70 €/m²

Weise darauf hin, dass dies nur Richtwerte sind.""" if language == "de" else
"""Create a rough cost estimate based on the m² values.
Use typical German market prices (2024):
- Flooring: 30-80 €/m²
- Painting: 15-35 €/m²
- Drywall: 40-70 €/m²

Note that these are only guideline values.""",

        InterpretationType.COMPARISON: """Vergleiche die Raumaufteilung mit typischen Gebäuden:
- Ist die Flächenverteilung üblich?
- Gibt es ungewöhnliche Verhältnisse?
- Wie steht das Gebäude im Vergleich zu Standards?""" if language == "de" else
"""Compare the room layout with typical buildings:
- Is the area distribution typical?
- Are there unusual ratios?
- How does the building compare to standards?""",

        InterpretationType.FULL_REPORT: """Erstelle einen vollständigen Bericht mit:
1. Zusammenfassung der Extraktion
2. Detaillierte Raumaufstellung nach Kategorie
3. Praktische Tipps für die Bauausführung
4. Grobe Kostenschätzung (mit Hinweis auf Richtwerte)
5. Empfehlungen für die Materialplanung""" if language == "de" else
"""Create a full report with:
1. Extraction summary
2. Detailed room breakdown by category
3. Practical tips for construction
4. Rough cost estimate (noting these are guidelines)
5. Material planning recommendations""",
    }

    return base_context + "\n\n" + type_prompts.get(interpretation_type, type_prompts[InterpretationType.SUMMARY])


def _build_user_prompt(
    extraction_data: Dict[str, Any],
    interpretation_type: InterpretationType,
    language: str,
) -> str:
    """Build user prompt with extraction data."""

    # Format key metrics
    total_rooms = extraction_data.get("room_count", 0)
    total_area = extraction_data.get("total_area_m2", 0)
    total_counted = extraction_data.get("total_counted_m2", total_area)
    style = extraction_data.get("blueprint_style", "unknown")
    by_category = extraction_data.get("totals_by_category", {})

    # Format room list
    rooms = extraction_data.get("rooms", [])
    room_summary = []
    for room in rooms[:20]:  # Limit to first 20 rooms
        room_summary.append(f"- {room.get('room_number', 'N/A')}: {room.get('room_name', 'Unknown')} - {room.get('area_m2', 0)} m²")

    if len(rooms) > 20:
        room_summary.append(f"... und {len(rooms) - 20} weitere Räume")

    if language == "de":
        prompt = f"""Extrahierte Daten aus Grundriss (Stil: {style}):

**Gesamtübersicht:**
- Anzahl Räume: {total_rooms}
- Gesamtfläche: {total_area:.2f} m²
- Angerechnete Fläche: {total_counted:.2f} m²

**Nach Kategorie:**
{json.dumps(by_category, indent=2, ensure_ascii=False)}

**Räume:**
{chr(10).join(room_summary)}

Bitte erstelle die gewünschte Interpretation."""
    else:
        prompt = f"""Extracted data from floor plan (style: {style}):

**Overview:**
- Number of rooms: {total_rooms}
- Total area: {total_area:.2f} m²
- Counted area: {total_counted:.2f} m²

**By Category:**
{json.dumps(by_category, indent=2, ensure_ascii=False)}

**Rooms:**
{chr(10).join(room_summary)}

Please create the requested interpretation."""

    return prompt


def generate_summary(extraction_data: Dict[str, Any], language: str = "de") -> InterpretationResult:
    """Generate a summary of extraction results."""
    return interpret_extraction(extraction_data, InterpretationType.SUMMARY, language)


def generate_smart_tips(extraction_data: Dict[str, Any], language: str = "de") -> InterpretationResult:
    """Generate smart tips for construction professionals."""
    return interpret_extraction(extraction_data, InterpretationType.SMART_TIPS, language)


def generate_cost_estimate(extraction_data: Dict[str, Any], language: str = "de") -> InterpretationResult:
    """Generate a rough cost estimate based on areas."""
    return interpret_extraction(extraction_data, InterpretationType.COST_ESTIMATE, language)


def generate_full_report(extraction_data: Dict[str, Any], language: str = "de") -> InterpretationResult:
    """Generate a full interpretation report."""
    return interpret_extraction(extraction_data, InterpretationType.FULL_REPORT, language)


# =============================================================================
# Quick Summary (without API call)
# =============================================================================


def generate_quick_summary(extraction_data: Dict[str, Any], language: str = "de") -> str:
    """
    Generate a quick summary without using LLM API.

    This is a fallback for when API is not available or for quick previews.
    """
    total_rooms = extraction_data.get("room_count", 0)
    total_area = extraction_data.get("total_area_m2", 0)
    total_counted = extraction_data.get("total_counted_m2", total_area)
    style = extraction_data.get("blueprint_style", "unknown")
    by_category = extraction_data.get("totals_by_category", {})

    style_names = {
        "haardtring": "Wohngebäude (Haardtring)",
        "leiq": "Bürogebäude (LeiQ)",
        "omniturm": "Hochhaus (Omniturm)",
        "unknown": "Unbekannt",
    }

    if language == "de":
        lines = [
            f"📊 **Extraktionsergebnis**",
            f"",
            f"**Gebäudetyp:** {style_names.get(style, style)}",
            f"**Anzahl Räume:** {total_rooms}",
            f"**Gesamtfläche:** {total_area:,.2f} m²",
        ]

        if total_counted != total_area:
            lines.append(f"**Angerechnete Fläche:** {total_counted:,.2f} m² (nach Balkon-Faktor)")

        if by_category:
            lines.append("")
            lines.append("**Nach Kategorie:**")
            for cat, area in sorted(by_category.items(), key=lambda x: -x[1]):
                cat_name = {
                    "office": "Büro",
                    "residential": "Wohnen",
                    "circulation": "Verkehrsfläche",
                    "stairs": "Treppen",
                    "elevators": "Aufzüge",
                    "shafts": "Schächte",
                    "technical": "Technik",
                    "sanitary": "Sanitär",
                    "storage": "Lager",
                    "outdoor": "Außenfläche",
                    "other": "Sonstige",
                }.get(cat, cat)
                lines.append(f"- {cat_name}: {area:,.2f} m²")

        return "\n".join(lines)

    else:
        lines = [
            f"📊 **Extraction Result**",
            f"",
            f"**Building Type:** {style}",
            f"**Number of Rooms:** {total_rooms}",
            f"**Total Area:** {total_area:,.2f} m²",
        ]

        if total_counted != total_area:
            lines.append(f"**Counted Area:** {total_counted:,.2f} m² (after balcony factor)")

        if by_category:
            lines.append("")
            lines.append("**By Category:**")
            for cat, area in sorted(by_category.items(), key=lambda x: -x[1]):
                lines.append(f"- {cat}: {area:,.2f} m²")

        return "\n".join(lines)
