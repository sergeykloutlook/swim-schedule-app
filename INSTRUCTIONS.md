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

When showing parsed events, use this format:
```
[Child Name] @[Location Code] [Time Range]
```

Example:
```
Nastya @MICC 5:30 - 6:45pm
Kseniya @MW 4:00 - 5:15pm
Liza @PL 3:30 - 4:30pm
```

## Calendar Invite Details

Each calendar invite should include:
- **Title**: `[Child Name] Swimming Practice`
- **Location**: Full address of the pool/club
- **Time**: Parsed from the PDF schedule

## Notes

- Only show events for the three teams: JUN2, JUN1 B, JUN1 R
- Filter out any "OFF" days
- Map child names to their respective teams automatically
