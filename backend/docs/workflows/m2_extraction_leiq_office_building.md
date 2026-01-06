# m2 Extraction LeiQ Office Building

This document serves as a test reference for orientation and describes a workflow for extracting room areas (m²) from the LeiQ Office Building style blueprints.

## Context: SnapPlan Web Application

SnapPlan is a standalone web application for deterministic extraction of construction document data. The extraction runs purely on code (no AI/LLM during extraction) to ensure:
- 100% traceability
- Zero hallucination
- Reproducible results

**Architecture:**
1. **Extraction Layer** (this document): Deterministic Python code extracts m² values from PDFs
2. **Storage Layer**: Results stored in Supabase with full audit trail
3. **Interpretation Layer** (future): LLM API connected later to interpret/summarize measurements

## Blueprint Characteristics

- **Project**: LeiQ Office Building (Nordring, Offenbach)
- **Format**: German CAD-generated PDF with internal room stamps
- **Sample File**: `/Users/clarence/Desktop/SnapPlan/GRUNDRISSE BTB 2/HMA-ARC-5-UP-WP-00-B0-0001-07-v-Bauteil B - šbersichtsplan Grundriss Erdgeschoss.pdf`
- **Area Label**: `NRF:` prefix (Netto-Raumfläche = Net Room Floor area)
- **Room Stamps**: Located INSIDE the drawing area, often colliding with lines

## Room Stamp Structure

Each room has a stamp containing:
```
Room Number (e.g., B.00.2.002)
Room Name (e.g., Lobby)
NRF: XXX,XX m2
U: XX,XXX m (Umfang = Perimeter)
LH: X,XXX m (Lichte Höhe = Clear Height)
```

## Room Number Format

`B.00.2.002` = Building B, Floor 00 (Ground), Zone 2, Room 002

**Zone meanings (this project):**
- Zone 0: Circulation (stairs, elevators)
- Zone 1: Services (WC, technical rooms)
- Zone 2: Common areas (lobby, bike room)
- Zone 3: Ancillary (changing rooms, showers)

## Key Patterns

### 1. Area Pattern (NRF:)
Two variations in text extraction:
- **Same line**: `NRF: 176,99 m2`
- **Split lines**: `NRF:` on one line, `117,05 m2` on next line

### 2. Additional Measurements
Unlike Haardtring, this format includes:
- `U: XX,XXX m` - Perimeter (useful for drywall calculations)
- `LH: X,XXX m` - Clear height (useful for volume calculations)

### 3. Room Types (German)
| German | English | Category |
|--------|---------|----------|
| Lobby | Lobby | Common |
| Flur | Hallway | Circulation |
| TRH | Treppenhaus (Stairwell) | Circulation |
| Aufzug | Elevator | Circulation |
| WC D / WC H | WC Women/Men | Services |
| WC Beh | Accessible WC | Services |
| WC Vorraum | WC Anteroom | Services |
| Fahrradraum | Bike Room | Ancillary |
| Umkleide D/H | Changing Room W/M | Ancillary |
| Duschen | Showers | Ancillary |
| Müll | Waste Room | Services |
| IT Verteiler | IT Distribution | Technical |
| ELT-UV | Electrical Panel | Technical |
| Elektro Station | Electrical Station | Technical |
| GLT | Building Automation | Technical |
| FIZ | Fire Control Center | Technical |
| Lagerraum | Storage | Ancillary |
| Nutzungseinheit | Usable Unit | Office |
| Back Office | Back Office | Office |

## Extraction Algorithm

```python
import fitz
import re

def extract_leiq_rooms(pdf_path):
    """
    Extract room areas from LeiQ-style blueprints.

    This is deterministic code - no AI/LLM involved.
    All values come directly from PDF text extraction.
    """
    doc = fitz.open(pdf_path)
    page = doc[0]
    text = page.get_text()
    lines = [l.strip() for l in text.split('\n')]

    rooms = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for room number pattern: B.00.2.002 or B.00.0.A02
        room_match = re.match(r'^(B\.\d+\.[0-9A-Z]+\.[A-Z]?\d+)$', line)
        if room_match:
            room_num = room_match.group(1)

            # Look for room name on next line
            room_name = None
            if i+1 < len(lines):
                next_line = lines[i+1]
                if next_line and not re.match(r'^(NRF|U:|LH:|B\.|[\d,]+)', next_line):
                    room_name = next_line

            # Look for NRF area value below
            area = None
            perimeter = None
            height = None

            for j in range(i+1, min(len(lines), i+15)):
                # Pattern 1: NRF: XX,XX m2 on same line
                same_line_match = re.match(r'^NRF:\s*(\d+[,.]?\d*)\s*m[²2]?$', lines[j])
                if same_line_match:
                    area = float(same_line_match.group(1).replace(',', '.'))
                    continue

                # Pattern 2: NRF: on one line, value on next
                if lines[j] == 'NRF:' and j+1 < len(lines):
                    area_match = re.match(r'^(\d+[,.]?\d*)\s*m[²2]?$', lines[j+1])
                    if area_match:
                        area = float(area_match.group(1).replace(',', '.'))
                        continue

                # Get U (perimeter) - useful for drywall
                u_match = re.match(r'^U:\s*(\d+[,.]?\d*)\s*m$', lines[j])
                if u_match:
                    perimeter = float(u_match.group(1).replace(',', '.'))
                    continue

                # Get LH (height) - useful for volume
                lh_match = re.match(r'^LH:\s*(\d+[,.]?\d*)\s*m$', lines[j])
                if lh_match:
                    height = float(lh_match.group(1).replace(',', '.'))
                    continue

                # Stop if we hit another room number
                if re.match(r'^B\.\d+\.[0-9A-Z]+\.[A-Z]?\d+$', lines[j]):
                    break

            if area:
                rooms.append({
                    'room_number': room_num,
                    'room_name': room_name or 'Unknown',
                    'area_m2': area,
                    'perimeter_m': perimeter,
                    'height_m': height,
                    # Traceability
                    'source_pattern': 'NRF:',
                    'extraction_method': 'deterministic_text'
                })
        i += 1

    doc.close()
    return rooms
```

## Verified Test Results

Extracted from Ground Floor (Erdgeschoss):

**ZONE 0 - Circulation (7 rooms) - 71.71 m²**
1. B.00.0.A01 - Aufzug - 5.39 m²
2. B.00.0.A02 - Aufzug - 9.24 m²
3. B.00.0.T01 - TRH B1 - Treppe - 7.71 m²
4. B.00.0.T02 - TRH B2 - Treppe - 16.82 m²
5. B.00.0.T03 - TRH B3- Treppe - 16.79 m²
6. B.00.0.T04 - TRH B4 - Treppe - 7.92 m²
7. B.00.0.T41 - TRH B4.1 - Treppe - 7.84 m²

**ZONE 1 - Services (12 rooms) - 639.72 m²**
1. B.00.1.001 - TRH B1 - 54.18 m²
2. B.00.1.002 - Flur - 21.69 m²
3. B.00.1.003 - Müll - 35.52 m²
4. B.00.1.005 - WC D - 7.85 m²
5. B.00.1.006 - WC Vorraum - 3.70 m²
6. B.00.1.007 - WC Vorraum - 3.17 m²
7. B.00.1.008 - WC H - 5.70 m²
8. B.00.1.009 - IT Verteiler - 5.23 m²
9. B.00.1.010 - ELT-UV - 5.26 m²
10. B.00.1.014 - TRH B2 - 10.95 m²
11. B.00.1.018 - Nutzungseinheit - 336.57 m²
12. B.00.1.019 - Nutzungseinheit - 149.90 m²

**ZONE 2 - Common Areas (12 rooms) - 418.30 m²**
1. B.00.2.001 - Vorbereich AZ - 11.44 m²
2. B.00.2.002 - Lobby - 176.99 m²
3. B.00.2.004 - Back Office - 19.11 m²
4. B.00.2.005 - GLT - 3.05 m²
5. B.00.2.005 - FIZ - 2.80 m²
6. B.00.2.006 - Fahrradraum - 117.05 m²
7. B.00.2.007 - WC Beh - 5.92 m²
8. B.00.2.008 - Vorbereich AZ - 26.76 m²
9. B.00.2.009 - Umkleide D - 20.85 m²
10. B.00.2.010 - Umkleide H - 17.79 m²
11. B.00.2.011 - Elektro Station - 5.66 m²
12. B.00.2.012 - TRH B3 - 10.88 m²

**ZONE 3 - Ancillary (21 rooms) - 297.07 m²**
1. B.00.3.001 - TRH B4 - 3.17 m²
2. B.00.3.002 - Fahrradraum - 158.22 m²
3. B.00.3.003 - Elektro Station - 6.05 m²
4. B.00.3.004 - Duschen - 4.86 m²
5. B.00.3.005 - WC - 2.74 m²
6. B.00.3.006 - Flur - 1.66 m²
7. B.00.3.007 - Duschen - 4.28 m²
8. B.00.3.008 - Duschen - 4.52 m²
9. B.00.3.009 - WC - 2.74 m²
10. B.00.3.010 - Duschen - 3.45 m²
11. B.00.3.011 - Flur - 3.54 m²
12. B.00.3.012 - Umkleide D - 21.59 m²
13. B.00.3.013 - Duschen - 5.05 m²
14. B.00.3.014 - WC - 2.84 m²
15. B.00.3.015 - Duschen - 3.98 m²
16. B.00.3.016 - Duschen - 4.81 m²
17. B.00.3.017 - WC - 2.83 m²
18. B.00.3.018 - Duschen - 5.03 m²
19. B.00.3.019 - Umkleide H - 19.95 m²
20. B.00.3.020 - Flur Fahrrad - 11.66 m²
21. B.00.3.022 - Lagerraum - 24.10 m²

**GRAND TOTAL: 1,426.80 m² (52 rooms)**

## Comparison: Haardtring vs LeiQ

| Feature | Haardtring | LeiQ |
|---------|------------|------|
| Area label | F: | NRF: |
| Room number format | R2.E5.3.5 | B.00.2.002 |
| Room stamps location | External boxes | Inside drawings |
| Additional data | 50% balcony factor | U: (perimeter), LH: (height) |
| Building type | Residential | Office |
| Typical room types | Schlafen, Bad, Kochen | Lobby, WC, Fahrradraum |

## Web App Integration Notes

### API Endpoint
`POST /api/v1/gewerke/flooring/nrf`

### Request
```json
{
  "pdf_file": "<uploaded PDF>",
  "extraction_mode": "auto"  // auto-detects F: vs NRF: pattern
}
```

### Response Structure
```json
{
  "rooms": [
    {
      "room_number": "B.00.2.002",
      "room_name": "Lobby",
      "area_m2": 176.99,
      "perimeter_m": 80.44,
      "height_m": 7.17,
      "source_text": "NRF: 176,99 m2",
      "page": 0,
      "extraction_method": "deterministic_text"
    }
  ],
  "totals": {
    "total_area_m2": 1426.80,
    "room_count": 52
  },
  "metadata": {
    "pattern_detected": "NRF:",
    "blueprint_style": "leiq_internal_stamps"
  }
}
```

### Future LLM Integration
The extracted data will later be passed to an LLM API for:
- Summarizing room breakdown by category
- Generating cost estimates
- Answering natural language queries about the floor plan
- Comparing against building codes/standards

The LLM receives only the extracted JSON - never the raw PDF - ensuring all measurements remain traceable to deterministic extraction.

## Important Notes

1. **Internal stamps**: Room stamps are inside drawings, may overlap with lines
2. **Text extraction**: PyMuPDF handles overlapping elements well
3. **Split patterns**: `NRF:` and value often on separate lines
4. **German decimals**: Always convert `,` to `.` for parsing
5. **Perimeter data**: U: values useful for drywall calculations (perimeter × height)
6. **Height data**: LH: values useful for volume and HVAC calculations

## Related Files

- Service: `backend/app/services/room_area_extraction.py`
- Tests: `backend/tests/test_room_area_extraction.py`
- API Endpoint: `POST /api/v1/gewerke/flooring/nrf`
- Haardtring workflow: `backend/docs/workflows/m2_extraction_haardtring_riegel_building.md`
