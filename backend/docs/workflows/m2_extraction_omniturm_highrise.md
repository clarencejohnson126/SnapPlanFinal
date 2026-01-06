# m2 Extraction Omniturm Highrise

This document serves as a test reference for orientation and describes a workflow for extracting room areas (m²) from Omniturm Highrise style blueprints.

## Context: SnapPlan Web Application

SnapPlan is a standalone web application for deterministic extraction of construction document data. Target users: construction companies, construction managers, architects, and planners who need to create measurement take-offs (Aufmaß).

**Value Proposition:** Save hours of manual work by automatically extracting room areas from PDF blueprints with 100% traceability.

## Blueprint Characteristics

- **Project**: Omniturm Highrise (Frankfurt)
- **Format**: German CAD-generated PDF with internal room stamps
- **Sample File**: `/Users/clarence/Desktop/SnapPlan/PLANS/Omniturm_Grundrisse/TES_5AH_PGT_G_H33_W2_000_-HA.pdf`
- **Area Label**: `NGF:` prefix (Netto-Grundfläche = Net Floor Area)
- **Room Stamps**: Inside drawings, two distinct patterns

## Room Number Format

`33_b6.12` = Floor 33, Grid Position b6, Room 12

Alternative format: `BT1.EG.001` = Building Part 1, Ground Floor (EG), Room 001

## Key Patterns

### Pattern 1: Standard Rooms (Room Number First)
```
33_b6.12          <- Room number
Aufzugsvorr.      <- Room name
NGF:              <- Area label (may be on same line or split)
8,98 m2           <- Area value
UKRD: +136,40     <- Additional height data
```

### Pattern 2: Shaft Rooms (Reversed Order)
```
Schacht 12        <- Shaft name
Lüftungsschacht   <- Shaft type
5,64 m2           <- Area value
33_b6.21          <- Room number (comes AFTER area!)
```

This reversed pattern is unique to Omniturm-style blueprints.

### German Number Format
- Decimal comma: `8,98` = 8.98
- Thousands separator: `1.070,55` = 1070.55

## Room Types (German)

| German | English | Category |
|--------|---------|----------|
| Bürofläche | Office Area | Office |
| Aufzugsvorr. | Elevator Lobby | Elevators |
| Aufzugsschacht | Elevator Shaft | Elevators |
| Treppenhaus | Stairwell | Stairs |
| Flur | Hallway | Circulation |
| Schleuse | Airlock/Vestibule | Circulation |
| Elektro SV/AV | Electrical Room | Technical |
| Schacht | Shaft | Shafts |
| Lüftungsschacht | Ventilation Shaft | Shafts |
| Druckbelüftung | Pressurization Shaft | Shafts |
| Medienschacht | Media Shaft | Shafts |
| Medien Büros | Office Media Shaft | Shafts |

## Extraction Algorithm

```python
import fitz
import re

def extract_omniturm_rooms(pdf_path):
    """
    Extract room areas from Omniturm-style highrise blueprints.

    Handles two patterns:
    1. Standard: room_number -> name -> NGF: area
    2. Reversed (Schacht): name -> type -> area -> room_number
    """
    doc = fitz.open(pdf_path)
    page = doc[0]
    text = page.get_text()
    lines = [l.strip() for l in text.split('\n')]

    rooms = []
    processed = set()

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if this is a room number
        room_match = re.match(r'^(\d+_[a-z]\d+\.\d+|BT\d+\.[A-Z]+\.\d+)$', line)
        if room_match and line not in processed:
            room_num = line
            room_name = None
            area = None

            for j in range(i+1, min(len(lines), i+15)):
                curr = lines[j]

                # Stop if we hit another room number
                if re.match(r'^(\d+_[a-z]\d+\.\d+|BT\d+\.[A-Z]+\.\d+)$', curr):
                    break

                # Get room name
                if room_name is None and curr and not re.match(
                    r'^(NGF|UKRD|UKFD|OKFF|OKRF|LRH|[\d,]+\s*m|Schacht)', curr
                ):
                    room_name = curr

                # Get area - NGF: on same line
                ngf_same = re.match(r'^NGF:\s*([\d.,]+)\s*m[²2]?$', curr)
                if ngf_same:
                    area = parse_german_number(ngf_same.group(1))
                    break

                # Get area - NGF: split across lines
                if curr == 'NGF:' and j+1 < len(lines):
                    area_match = re.match(r'^([\d.,]+)\s*m[²2]?$', lines[j+1])
                    if area_match:
                        area = parse_german_number(area_match.group(1))
                        break

                # Special: Schacht pattern (reversed order)
                if re.match(r'^Schacht \d+$', curr):
                    room_name = curr
                    if j+2 < len(lines):
                        type_line = lines[j+1]
                        area_line = lines[j+2]
                        if not re.match(r'^[\d,]', type_line):
                            room_name = f'{curr} ({type_line})'
                        area_match = re.match(r'^([\d,]+)\s*m[²2]?$', area_line)
                        if area_match:
                            area = float(area_match.group(1).replace(',', '.'))
                            break

            if area:
                rooms.append({
                    'room_number': room_num,
                    'room_name': room_name or 'Unknown',
                    'area_m2': area,
                    'source_pattern': 'NGF:',
                    'extraction_method': 'deterministic_text'
                })
                processed.add(room_num)

        i += 1

    doc.close()
    return rooms

def parse_german_number(s):
    """Convert German number format to float: 1.070,55 -> 1070.55"""
    if '.' in s and ',' in s:
        return float(s.replace('.', '').replace(',', '.'))
    return float(s.replace(',', '.'))
```

## Verified Test Results

Extracted from Floor 33:

**OFFICE (1 room) - 1,070.55 m²**
1. 33_a3.17 - Bürofläche - 1,070.55 m²

**ELEVATORS (7 rooms) - 143.91 m²**
1. 33_b6.12 - Aufzugsvorr. - 8.98 m²
2. 33_b6.18 - Aufzugsvorr. - 53.89 m²
3. 33_c1.16 - Aufzugsschacht - 17.67 m²
4. 33_c1.21 - Aufzugsschacht - 17.67 m²
5. 33_c2.12 - Aufzugsschacht - 9.12 m²
6. 33_c6.16 - Aufzugsschacht - 18.29 m²
7. 33_c6.21 - Aufzugsschacht - 18.29 m²

**STAIRS (3 rooms) - 61.40 m²**
1. 33_c1.23 - Treppenhaus 2 - 17.59 m²
2. 33_d1.13 - Treppenhaus 1 - 18.58 m²
3. BT1.EG.001 - Treppenhaus - 25.23 m²

**CIRCULATION (6 rooms) - 47.47 m²**
1. 33_b6.14 - Flur - 10.62 m²
2. 33_c2.14 - Schleuse - 10.60 m²
3. 33_c5.11 - Flur - 2.90 m²
4. 33_c5.25 - Flur - 2.45 m²
5. 33_c6.23 - Schleuse - 10.28 m²
6. 33_d3.23 - Flur - 10.62 m²

**SHAFTS (12 rooms) - 46.00 m²**
1. 33_b5.23 - Schacht 11 (Lüftungsschacht) - 2.21 m²
2. 33_b6.11 - Schacht 01 (Medien Büros) - 2.44 m²
3. 33_b6.21 - Schacht 12 (Lüftungsschacht) - 5.64 m²
4. 33_b6.26 - Schacht 10 (Lüftungsschacht) - 8.88 m²
5. 33_c4.24 - Schacht 08 (Druckbelüftung) - 1.02 m²
6. 33_c4.26 - Schacht 09 (Druckbelüftung) - 1.00 m²
7. 33_c6.11 - Schacht 02 (Druckbelüftung) - 1.26 m²
8. 33_c6.13 - Schacht 04 (Druckbelüftung) - 1.02 m²
9. 33_d1.11 - Schacht 03 (Lüftungsschacht) - 12.18 m²
10. 33_d1.26 - Schacht 07 (Medien Büros) - 2.44 m²
11. 33_d4.16 - Schacht 06 (Lüftungsschacht) - 5.70 m²
12. 33_d5.13 - Schacht 05 (Medienschacht) - 2.21 m²

**TECHNICAL (2 rooms) - 15.04 m²**
1. 33_d1.25 - Elektro SV - 6.39 m²
2. 33_d3.25 - Elektro AV - 8.65 m²

**GRAND TOTAL: 1,384.37 m² (31 rooms)**

## Comparison: All Three Blueprint Styles

| Feature | Haardtring | LeiQ | Omniturm |
|---------|------------|------|----------|
| Area label | F: | NRF: | NGF: |
| Room number format | R2.E5.3.5 | B.00.2.002 | 33_b6.12 |
| Building type | Residential | Office | Highrise |
| Room stamps | External boxes | Inside drawings | Inside drawings |
| Special patterns | 50% balcony factor | U: perimeter, LH: height | Schacht reversed order |
| Number format | German comma | German comma | German comma + thousands |

## Pattern Detection Strategy

For the web app, implement auto-detection:

```python
def detect_blueprint_style(text):
    """Auto-detect blueprint style based on patterns found."""

    # Check area label patterns
    has_f = bool(re.search(r'\bF:\s*\d', text))
    has_nrf = bool(re.search(r'\bNRF:\s*\d', text))
    has_ngf = bool(re.search(r'\bNGF:\s*\d', text))

    # Check room number patterns
    has_r_pattern = bool(re.search(r'\bR\d+\.E\d+\.\d+\.\d+\b', text))
    has_b_pattern = bool(re.search(r'\bB\.\d+\.\d+\.\d+\b', text))
    has_grid_pattern = bool(re.search(r'\b\d+_[a-z]\d+\.\d+\b', text))

    if has_f and has_r_pattern:
        return 'haardtring'
    elif has_nrf and has_b_pattern:
        return 'leiq'
    elif has_ngf and has_grid_pattern:
        return 'omniturm'
    else:
        return 'unknown'
```

## Important Notes

1. **Reversed Schacht pattern**: Room number comes AFTER area value
2. **German thousands separator**: `1.070,55` must be parsed correctly
3. **Grid-based room numbers**: `33_b6.12` uses floor + grid position
4. **Large office areas**: Single rooms can exceed 1,000 m²
5. **Multiple room number formats**: Same blueprint may have `33_xx.xx` and `BT1.XX.XXX`

## Related Files

- Service: `backend/app/services/room_area_extraction.py`
- API Endpoint: `POST /api/v1/gewerke/flooring/nrf`
- Haardtring workflow: `backend/docs/workflows/m2_extraction_haardtring_riegel_building.md`
- LeiQ workflow: `backend/docs/workflows/m2_extraction_leiq_office_building.md`
