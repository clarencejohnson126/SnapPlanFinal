# m2 Extraction Haardtring Riegel Building

This document serves as a test reference for orientation  and describes a workflow for extracting room areas (m²) from the example project Haardtring Riegel Building style blueprints.

## Blueprint Characteristics

- **Format**: German CAD-generated PDF with external room stamp boxes
- **Sample File**: `/Users/clarence/Desktop/SnapPlan/PLANS/Haardtring_Grundriss/DAR_5_ARC_BA4_R2_02_GR_E501_050_-J_F.pdf`
- **Area Label**: `F:` prefix (from German "Fläche" = Area)
- **Room Stamps**: Located outside the drawing area in boxes

## Room Stamp Structure

Each room has a stamp box containing:
```
Room Name (e.g., "Schlafen", "Bad", "Wohnen/Essen")
Room Number (e.g., "R2.E5.3.5")
F: XX,XX m2
BA: XX (Bodenaufbau - floor construction)
B: XX (Bodenbelag - floor covering)
W: XX (Wandbelag - wall covering)
D: XX (Deckenbelag - ceiling covering)
```

## Room Number Format

`R2.E5.3.5` = Building R2, Floor E5, Unit 3, Room 5

## Key Patterns

### 1. Area Pattern (F:)
Two variations in text extraction:
- **Same line**: `F: 13,49 m2`
- **Split lines**: `F:` on one line, `13,49 m2` on next line

### 2. Balcony 50% Factor
Outdoor spaces (Dachterrasse, Terrasse, Balkon) show:
```
F: 14,03 m2      <- Raw area
50%: 7,01 m2     <- Counted area (50% factor applied)
```

### 3. Room Types (German)
| German | English | Is Outdoor |
|--------|---------|------------|
| Schlafen | Bedroom | No |
| Bad | Bathroom | No |
| Gästebad | Guest bathroom | No |
| Wohnen/Essen | Living/Dining | No |
| Kochen | Kitchen | No |
| Diele | Entry hall | No |
| Flur | Hallway | No |
| HWR/AR | Utility room | No |
| Zimmer | Room | No |
| Dachterrasse | Roof terrace | Yes (50%) |
| Terrasse | Terrace | Yes (50%) |
| Balkon | Balcony | Yes (50%) |

## Extraction Algorithm

```python
import fitz
import re

def extract_haardtring_rooms(pdf_path):
    doc = fitz.open(pdf_path)
    page = doc[0]
    text = page.get_text()
    lines = [l.strip() for l in text.split('\n')]

    rooms = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for room number pattern: R2.E5.3.5
        room_match = re.match(r'^(R\d+\.E\d+\.\d+\.\d+)$', line)
        if room_match:
            room_num = room_match.group(1)

            # Look for room name above (go back up to 5 lines)
            room_name = None
            for j in range(i-1, max(0, i-5), -1):
                prev = lines[j]
                if prev and not re.match(r'^(BA:|B:|W:|D:|F:|[\d,]+|OK|UK|k\.A\.|\d+;\s*\d+)', prev):
                    room_name = prev
                    break

            # Look for F: area value below
            area = None
            balcony_area = None

            for j in range(i+1, min(len(lines), i+15)):
                # Pattern 1: F: XX,XX m2 on same line
                same_line_match = re.match(r'^F:\s*(\d+[,.]?\d*)\s*m[²2]?$', lines[j])
                if same_line_match:
                    area = float(same_line_match.group(1).replace(',', '.'))
                    # Check for 50% on next line
                    if j+1 < len(lines):
                        balcony_match = re.match(r'^50%:\s*(\d+[,.]?\d*)\s*m[²2]?$', lines[j+1])
                        if balcony_match:
                            balcony_area = float(balcony_match.group(1).replace(',', '.'))
                    break

                # Pattern 2: F: on one line, value on next
                if lines[j] == 'F:' and j+1 < len(lines):
                    area_match = re.match(r'^(\d+[,.]?\d*)\s*m[²2]?$', lines[j+1])
                    if area_match:
                        area = float(area_match.group(1).replace(',', '.'))
                        if j+2 < len(lines):
                            balcony_match = re.match(r'^50%:\s*(\d+[,.]?\d*)\s*m[²2]?$', lines[j+2])
                            if balcony_match:
                                balcony_area = float(balcony_match.group(1).replace(',', '.'))
                        break

                # Stop if we hit another room number
                if re.match(r'^R\d+\.E\d+\.\d+\.\d+$', lines[j]):
                    break

            if area:
                rooms.append({
                    'room_number': room_num,
                    'room_name': room_name or 'Unknown',
                    'area_m2': area,
                    'balcony_50pct': balcony_area
                })
        i += 1

    doc.close()
    return rooms
```

## Verified Test Results

Extracted from floor E5 (5th floor):

**UNIT R1.E5.2 (3 rooms)**
1. R1.E5.2.9 - Wohnen/Essen - 26.65 m²
2. R1.E5.2.10 - Unknown - 6.64 m²
3. R1.E5.2.11 - Terrasse/Balkon - 47.89 m² (50%: 23.95 m²)

**UNIT R2.E5.1 (12 rooms)**
1. R2.E5.1.1 - Diele - 3.32 m²
2. R2.E5.1.2 - Wohnen/Essen - 27.04 m²
3. R2.E5.1.3 - Flur - 3.38 m²
4. R2.E5.1.4 - Bad - 5.69 m²
5. R2.E5.1.5 - Schlafen - 18.69 m²
6. R2.E5.1.6 - Kochen - 6.99 m²
7. R2.E5.1.7 - Zimmer - 10.51 m²
8. R2.E5.1.8 - Zimmer - 11.91 m²
9. R2.E5.1.9 - Gästebad - 4.18 m²
10. R2.E5.1.10 - HWR/AR - 2.12 m²
11. R2.E5.1.11 - Flur - 2.59 m²
12. R2.E5.1.12 - Dachterrasse - 49.95 m²

**UNIT R2.E5.2 (7 rooms)**
1. R2.E5.2.1 - Diele - 3.43 m²
2. R2.E5.2.2 - HWR/AR - 2.10 m²
3. R2.E5.2.3 - Kochen - 7.26 m²
4. R2.E5.2.4 - Wohnen/Essen - 23.41 m²
5. R2.E5.2.5 - Schlafen - 13.49 m²
6. R2.E5.2.6 - Bad - 6.47 m²
7. R2.E5.2.7 - Dachterrasse - 14.03 m² (50%: 7.01 m²)

**UNIT R2.E5.3 (7 rooms)**
1. R2.E5.3.1 - Diele - 3.43 m²
2. R2.E5.3.2 - HWR/AR - 2.10 m²
3. R2.E5.3.3 - Kochen - 7.26 m²
4. R2.E5.3.4 - Wohnen/Essen - 23.41 m²
5. R2.E5.3.5 - Schlafen - 13.49 m²
6. R2.E5.3.6 - Bad - 6.47 m²
7. R2.E5.3.7 - Dachterrasse - 14.03 m² (50%: 7.01 m²)

**TOTALS**
- 29 rooms across 4 units
- Raw area: 367.93 m²
- Counted area (with 50% balcony factor): 329.95 m²

## Important Notes

1. **Text extraction quirks**: PyMuPDF's `get_text()` may split `F: 13,49 m2` across two lines
2. **German decimal comma**: Always convert `,` to `.` for float parsing
3. **Room stamps are external**: Areas are in boxes outside the floor plan drawing
4. **50% factor**: When present, the blueprint shows both raw and factored values
5. **Different blueprints may vary**: Other projects may have areas INSIDE drawings, obscured by lines

## Related Files

- Service: `backend/app/services/room_area_extraction.py`
- Tests: `backend/tests/test_room_area_extraction.py`
- API Endpoint: `POST /api/v1/gewerke/flooring/nrf`
