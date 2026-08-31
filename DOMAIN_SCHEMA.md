# Domain Schema: Community Sports League Fixtures

**Domain ID:** 7

**Entity:** Fixture (a scheduled match between two teams)

## Fields

| Field | Type | Description |
|---|---|---|
| `fixture_name` | text (primary) | Name identifying the match, e.g. “Milpitas Lions vs San Jose Tigers” |
| `teams_players` | text (secondary) | Teams and players involved in the fixture |
| `submitter_email` | email | Email of the person submitting the fixture |
| `description` | textarea | Match details, notes, or rules |
| `category` | dropdown | Sport type for the fixture |
| `agree_terms` | checkbox | Agreement to terms and conditions |

## Category Values (Sport Type)

1. Soccer
2. Basketball
3. Volleyball
4. Cricket