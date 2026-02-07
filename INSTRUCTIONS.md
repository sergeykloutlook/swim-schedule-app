# Swim Schedule App - Configuration Instructions

## Children and Teams

| Child | Team Code | Team Full Name |
|-------|-----------|----------------|
| Nastya | JUN2 | Junior 2 |
| Kseniya | JUN1 B | Junior 1 Black |
| Liza | JUN1 R | Junior 1 Red |

## PDF Parsing Format

The PDF schedule format is:
1. **Team** (first)
2. **Time** (second)
3. **Place** (third)

When "OFF" appears in the calendar, it means no practice that day - skip it.

## Locations

| Code | Full Name | Address |
|------|-----------|---------|
| MICC | Mercer Island Country Club | 8700 SE 71st St, Mercer Island, WA 98040 |
| MW | Mary Wayte Swimming Pool | 8815 SE 40th St, Mercer Island, WA 98040 |
| MIBC | Mercer Island Beach Club | 8326 Avalon Dr, Mercer Island, WA 98040 |
| PL | Phantom Lake Bath & Tennis Club | 15810 SE 24th St, Bellevue, WA 98008 |

## Display Format

When showing parsed events, the title should be:
```
[Child Name] @[Location Code] [Time Range]
```

Example title:
```
Liza @MICC 5:00 - 6:00 pm
```

Below the title, show:
- **Date:** The date of the practice
- **Time:** The time range
- **Location:** Full address of the pool/club

## Calendar Invite Details

Each calendar invite should include:
- **Title/Subject**: `Liza @MICC 5:00 - 6:00 pm` (same as display format)
- **Location**: Full address of the pool/club
- **Time**: Parsed from the PDF schedule

## Notes

- Only show events for the three teams: JUN2, JUN1 B, JUN1 R
- Filter out any "OFF" days
- Map child names to their respective teams automatically
