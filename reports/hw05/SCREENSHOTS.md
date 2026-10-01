# HW5 screenshot checklist

Which images have been captured, and which requirements are covered by
real console text instead. All images live in `reports/hw05/screenshots/`
and are referenced from the report as
`\includegraphics{screenshots/<name>.png}`.

Every Postman shot has the collection name
"Uday Patel - DATA-260 HW5 Part 1.II" visible in the sidebar and/or
"udai patel's Workspace" in the title bar, which satisfies the
name-must-be-visible requirement.

## Part 1.II - Postman (required: the assignment names Postman) - DONE

Captured with `reports/hw05/postman/HW5_Part1_API.postman_collection.json`
against the live server on PORT_BASE 8871 and the real `s9871_rel`
database, 2026-09-28 between 21:32 and 21:58 local.

| Collection request | Observed | File |
|---|---|---|
| 00 - Login | 200 OK | `p1_login.png` |
| 01 - Team CREATE | 201 Created, id 17, TM-0500 | `p1_team_create.png` |
| 02 - Team LIST with pagination | 200 OK, page=1 page_size=3 | `p1_team_list_paginated.png` |
| 03 - Team GET one | 200 OK | `p1_team_get_one.png` |
| 04 - Team UPDATE | 200 OK, updated_at advanced | `p1_team_update.png` |
| 05 - Fixture CREATE | 201 Created, spots_available defaulted to 22 | `p1_fixture_create.png` |
| 06 - Fixture LIST | 200 OK, 1.23 MB | `p1_fixture_list.png` |
| 07 - Fixture GET one | 200 OK | `p1_fixture_get_one.png` |
| 08 - Fixture UPDATE | 200 OK, spots_available 22 -> 14 | `p1_fixture_update.png` |
| 09 - RELATIONSHIP QUERY | 200 OK, fixture_count 1 | `p1_relationship_query.png` |
| 10 - ERROR resource not found | 404 Not Found | `p1_error_404_not_found.png` |
| 11 - ERROR validation | 422, string_pattern_mismatch on team_code | `p1_error_422_validation.png` |
| 12 - ERROR constraint violation | 409 Conflict, delete refused | `p1_error_409_constraint.png` |
| 13 - Fixture DELETE | 200 OK, deleted_id 5009 | `p1_fixture_delete.png` |
| 14 - Team DELETE | 200 OK, deleted_id 17 | `p1_team_delete.png` |

Known limitation, accepted rather than hidden:

- `p1_team_list_paginated.png` shows the paginated request (`page=1`,
  `page_size=3` in both the URL and the Params grid) and a 200 response,
  but the response pane is not scrolled far enough to show the
  `page` / `page_size` / `total` / `total_pages` envelope fields. The
  complete response, including those fields, is inlined in the report as
  real captured text from `RUN_LOG.txt` section 1d, so the evidence is
  present in the write-up even though this one image stops short of it.
- The POST/PUT shots have the Params tab selected, so the request JSON is
  not in frame. Part 1.II asks only for a screenshot of each action; the
  request bodies are inlined as listings in the report.

## Part 1.II - database - COVERED BY TEXT, no image

Requirement: "Submit a screenshot of your DB."

No specific tool is named, so the real `SHOW CREATE TABLE` output for
`teams` and `fixtures` in `RUN_LOG.txt` section 1a is used, inlined in the
report as a listing. `reports/hw05/sql/db_screenshot_queries.sql` remains
available if an image is wanted later.

## Part 1.III - Redux client - DONE

The requirement is "the code snippet and the UI output together, in the same
frame". Per the rule now in CLAUDE.md, that is satisfied in the **report
layout** rather than by a combined image: in each figure the relevant
snippet goes in a `lstlisting` block directly above the screenshot, and both
sit under one shared `\small \textit{Figure N: ...}` caption. The images are
browser-only; the editor is not in shot.

| Feature | `lstlisting` above the image | Image |
|---|---|---|
| Home | `Home.jsx` lines 18-45, the `useSelector` block | `p1_redux_home.png` |
| Create | `fixturesSlice.js` lines 24-34, the `createFixture` thunk | `p1_redux_create.png` |
| Update | `fixturesSlice.js` lines 36-46, the `updateFixture` thunk | `p1_redux_update.png` |
| Delete | `fixturesSlice.js` lines 48-60, the `deleteFixture` thunk | `p1_redux_delete.png` |

What each image actually shows, verified by reading the files:

- `p1_redux_home.png` - Fixture Board, "5001 fixtures in Redux state -
  showing 1-25", the full table with per-row Edit and Delete.
- `p1_redux_create.png` - Add Fixture form, code pre-filled to the next free
  `FX-9871-05005`, spots defaulted to 22, populated team dropdown.
- `p1_redux_update.png` - Update Fixture #3 with the ID typed in and every
  field prefilled from Redux state, which is the select-by-ID requirement.
- `p1_redux_delete.png` - Home with the per-row delete confirmation dialog
  open: "Delete fixture #3 (FX-9871-00003)?".

To reproduce the running app: start the backend on 8871, run `npm run dev`
in `client/`, log in as the demo admin.

### Verification screenshots (not report deliverables)

`test_redux_ui.py` saves these automatically while it drives the real
browser. They are evidence that the UI was genuinely exercised, not
substitutes for the four hand-composed images above:

- `redux_auto_home.png` - 5001 fixtures in Redux state, page 1 of 201
- `redux_auto_create.png` - new fixture visible and highlighted
- `redux_auto_create_error.png` - the API's 422 rendered on the form
- `redux_auto_update.png` - Home opened on page 201, updated row highlighted
- `redux_auto_delete.png` - row removed from table and from MySQL

## Later parts - NOT YET CAPTURED

- Part 2A: one MCP Inspector screenshot per tool, 4 total.
- Part 2B: one successful and one intentionally invalid call per domain
  tool, 6 total.
- Part 4: one terminal screenshot of the offline test runner showing
  PASS/FAIL per test and the final X/Y summary.

No screenshot is ever described in the report unless the real file exists
in `reports/hw05/screenshots/`.
