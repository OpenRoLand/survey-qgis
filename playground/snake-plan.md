# Web Map Temporal Filtering and Snake Implementation Plan

## Goal

Add an optional temporal mode to the map in the sibling
`openroland-survey-core` web application. The mode must expose the same useful
semantics as the QGIS plugin:

- compute continuous survey intervals from observation timestamps;
- filter which intervals participate in the map;
- move a fixed-size window through the selected time range;
- play, pause, and step the window in either direction;
- optionally draw a snake between consecutive observations; and
- keep the newest visible snake segment red and the oldest blue.

The existing non-temporal map remains the default. No QGIS installation is
required to serve or use the web application.

The implementation target is `D:\prog\openroland\openroland-survey-core`. This
file lives in the QGIS repository because that repository is the reference
implementation.

## Existing Behavior and Reusable Semantics

### QGIS reference

The web implementation should deliberately preserve these behaviors:

- `survey_qgis/core/observations.py` creates one observation for each
  `(survey_point_id, source_file_id)` association. It prefers
  `survey_point_sources.observed_at` and falls back to
  `survey_points.observed_at_utc`.
- `survey_qgis/core/intervals.py` sorts observations by time and starts a
  new interval only when the gap is strictly greater than the configured
  threshold. The default threshold is 1,800 seconds.
- Interval computation is global by default. The optional
  `group_by_source` mode computes independent interval streams for each
  source file.
- Date filtering includes every interval that overlaps the inclusive date
  range.
- `survey_qgis/core/snake.py` connects consecutive observations only when
  they belong to the same interval. It never bridges an interval gap.
- `survey_qgis/layers/time_controller.py` uses a 300-second default window,
  a step equal to the window size, and one playback frame per second.
- `survey_qgis/layers/snake_overlay.py` includes a segment when it overlaps
  the current window. It recolors the visible set from blue to red after
  every window change, with a single visible segment always red.
- Temporal filtering and the snake are independent switches. Disabling the
  time window restores all observations from the selected intervals.

### Current web map

The current web path is canonical-point based:

- `GET /api/map/points` returns paged GeoJSON for `survey_points`.
- `frontend/src/mapFeed.ts` loads every page with stale-request
  cancellation.
- `frontend/src/useMapFeed.ts` exposes progress and lifecycle state.
- `frontend/src/pages/MapPage.tsx` incrementally adds circle markers to a
  Leaflet marker cluster, fits only the first batch, and opens
  `PointDetailDrawer` from a marker.
- Marker fill and size come from the existing precision helpers.

Temporal behavior cannot be implemented correctly from this response alone.
A canonical point can have several source associations with different
timestamps, while the QGIS behavior is observation based.

## Architecture Decisions

### Use an observation feed, not QGIS-owned tables

Add a read-only web endpoint over `survey_point_sources` joined to
`survey_points`. Do not require `survey_observations`, `survey_intervals`, or
`survey_qgis_config` to exist. Those tables are currently an optional QGIS
extension and may not exist in a database used only by the web application.

This also avoids:

- modifying a GeoPackage merely because a browser enabled temporal mode;
- making a gap threshold chosen by one browser affect other browsers;
- racing with QGIS when both applications use the same GeoPackage; and
- increasing the core schema version for a presentation feature.

The browser already loads the complete canonical map feed. Load the complete
timed-observation feed on demand and compute interval membership in pure
TypeScript. Gap and grouping changes can then be applied immediately without
another request or a database write.

### Keep canonical and temporal modes distinct

With temporal mode off, preserve the current canonical map exactly. With it
on, render one marker per timed point-source observation. A canonical point
seen in two source files may therefore have two observations, possibly at
the same location.

Untimed observations are excluded from interval, window, and snake logic.
The controls must state how many were omitted. Returning to canonical mode
shows all mappable canonical points again, including points without time.

### Use UTC for all calculations

Normalize server timestamps to aware UTC values and serialize them with a
`Z` or explicit `+00:00` offset. Perform interval splitting and window
comparisons using epoch milliseconds. Label all date and time controls as
UTC so browser locale and daylight-saving transitions cannot change the
result.

### Keep the first release dependency-free

Material UI already provides switches, checkboxes, date inputs, and a
slider. Leaflet already provides polylines and layer groups. No timeline,
animation, or drawing package is required.

## User Experience

Add a collapsed `Temporal` card above the map. Its master switch defaults to
off. The existing map starts loading as it does today.

On first enable:

1. Fetch the paged timed-observation feed and show independent progress and
   cancel controls.
2. Initialize the date filter to the data minimum and maximum.
3. Compute intervals using a 1,800-second gap without source grouping.
4. Select every interval in the date filter.
5. Switch the Leaflet layer from canonical markers to observation markers.
6. Keep time-window filtering off until the user enables it.

The card should contain three compact sections.

### Intervals section

- UTC start and end date fields with `Min`, `Max`, and `Apply date filter`
  actions.
- A scrollable checklist. Each row shows start, end, duration, observation
  count, and either `all sources` or the source file ID.
- `Select all` and `Select none` actions.
- A gap threshold in seconds, constrained to 60 seconds through seven days.
- A `Group by source file` checkbox.
- A `Recompute intervals` action. Recompute is local and must not refetch.

Date filtering controls which intervals appear in the checklist. It uses
overlap semantics, rather than requiring an interval to be fully contained.
Changing checked intervals immediately changes temporal markers and the
snake. Unlike the current QGIS empty-selection edge case, no selection means
no temporal markers and no snake; it must not mean "all intervals."

### Sliding-window section

- A `Filter by time window` switch, defaulting to off.
- A window-size field in seconds, defaulting to 300 and constrained to one
  second through one day.
- `Step back`, `Play`, `Pause`, and `Step forward` buttons.
- An `Apply range from selected intervals` button.
- A slider spanning the applied minimum start through maximum end.
- A text label showing the exact inclusive UTC window.

Applying the range sets the cursor to the earliest selected interval start.
Each step advances by the current window size. Playback advances one step per
second and pauses at the end. Manual slider movement pauses playback. The
cursor is clamped whenever the range or window size changes.

As in QGIS, the overall range may contain gaps between selected intervals.
Windows inside a gap legitimately show no points. Enabling the time filter
without an applied range leaves all selected observations visible and shows
an actionable hint.

### Snake section

- A `Show snake` checkbox, enabled by default inside temporal mode.
- A small blue-to-red legend labeled `older` and `newer`.
- A visible segment count so an empty snake is distinguishable from a
  rendering failure.

When the time filter is off, show all snake segments in selected intervals.
When it is on, show a whole segment if its time span overlaps the inclusive
window. Recompute the blue-to-red ramp over only the currently visible
segments after every selection or window change.

## Backend API Contract

### New endpoint

Register `GET /api/map/observations` beside `/api/map/points` in
`openroland_survey/web.py`.

Query parameters:

- `cursor`: optional opaque composite cursor;
- `page_size`: the existing map default of 2,000 and maximum of 5,000.

Use a stable keyset order of `(source_file_id, survey_point_id)`. Encode the
two integers in a validated cursor such as `7:42`; do not use offset
pagination. The next-page predicate is:

```sql
source_file_id > :source_id
OR (
    source_file_id = :source_id
    AND survey_point_id > :point_id
)
```

Reject malformed and negative cursor components with a client-safe 422
response. Do not interpolate cursor values into SQL.

### Observation selection

Build the query from `SurveyPointSource` joined to `SurveyPoint` and the
existing source-count subquery. Define observation time as:

```sql
COALESCE(
    survey_point_sources.observed_at,
    survey_points.observed_at_utc
)
```

Return rows only when the coalesced time, latitude, and longitude are not
null. Use canonical name, code, status, and precision fields, matching the
QGIS materialization behavior. One association with `occurrence_count > 1`
still produces one observation in this release, which matches QGIS. Expanding
`observations_json` into multiple fixes is a separate feature.

### Response schemas

Add separate Pydantic types in `openroland_survey/schemas.py` rather than
overloading `MapFeature`. A representative response is:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [24.5, 46.5]
      },
      "properties": {
        "observation_key": "7:42",
        "point_id": 42,
        "source_file_id": 7,
        "observed_at": "2026-07-21T09:30:00Z",
        "name": "P42",
        "code": null,
        "status": "fixed",
        "source_count": 2,
        "occurrence_count": 1,
        "hrms": 0.01,
        "vrms": 0.02,
        "hdop": 1.1,
        "pdop": 1.5
      }
    }
  ],
  "next_cursor": "7:42",
  "has_more": true,
  "total_timed": 2500,
  "total_untimed": 12,
  "earliest_observed_at": "2026-07-20T07:00:00Z",
  "latest_observed_at": "2026-07-21T16:00:00Z"
}
```

`total_untimed` counts mappable point-source associations whose association
and canonical fallback timestamps are both null. Bounds cover only returned,
timed observations. Empty data returns zero totals, null bounds, and an empty
feature list.

Add matching interfaces and a `getMapObservations` function in
`frontend/src/types.ts` and `frontend/src/api.ts`.

## Pure Temporal Model

Create `frontend/src/temporalMap.ts`. Keep all calculations independent of
React and Leaflet so they can be exhaustively unit tested.

Define these model types:

- `TemporalObservation`: parsed observation key, point ID, source ID,
  timestamp in milliseconds, coordinates, and original feature;
- `SurveyInterval`: stable session-local ID, optional source ID, start, end,
  observation count, and ordered observation keys;
- `SnakeSegment`: interval ID, endpoint keys and coordinates, start, and end;
- `TemporalWindow`: inclusive start and end epoch milliseconds.

Implement the following pure functions:

1. `normalizeObservations(features)` validates dates and sorts by
   `(timestamp, sourceFileId, pointId)` for deterministic equal-time order.
2. `buildIntervals(observations, gapSeconds, groupBySource)` reproduces the
   QGIS split rule. A gap equal to the threshold remains in one interval.
3. `filterIntervalsByDate(intervals, startDate, endDate)` applies inclusive
   overlap semantics using UTC day boundaries.
4. `buildSnakeSegments(observations, selectedIntervalIds)` connects only
   consecutive observations in one interval.
5. `observationsForSelection(...)` returns all selected observations or the
   subset inside the active inclusive window.
6. `segmentsForWindow(...)` keeps segments that overlap the active window.
7. `snakeSegmentColor(index, count)` copies the QGIS `(0, 70, 255)` to
   `(220, 20, 20)` interpolation and makes one segment red.
8. `clampCursor(...)` and `stepCursor(...)` centralize range-end behavior.

Interval IDs need only be stable for one computed result. Generate them from
the source grouping key, chronological ordinal, and start time. Reset the
selection when gap or grouping changes rather than trying to map old IDs to
new intervals.

For large data sets, retain the globally time-sorted observations and a
parallel timestamp array. Use binary search to locate the candidate window
slice before applying the selected-interval set. Avoid filtering every
observation on every playback tick.

## Frontend Data Flow

### Feed and hook

Refactor `frontend/src/mapFeed.ts` just enough to share its paging and
cancellation machinery with an observation feed. Preserve the exported
`MapFeedController` API so existing callers and tests keep working.

Add a temporal controller or typed wrapper that:

- passes the composite cursor returned by the server;
- accumulates observation features page by page;
- reports timed and untimed totals and bounds;
- discards any page that resolves after cancellation or reload; and
- exposes API error messages consistently with the canonical feed.

Add `frontend/src/useTemporalMapData.ts` to own feed lifecycle and derived
state. It should load only when temporal mode is first enabled, expose an
explicit reload, and memoize interval recomputation. Do not compute or expose
partially stable interval IDs while pages are still arriving; show loading
progress, then publish the complete temporal model atomically.

Keep these view preferences in `localStorage` with validation and defaults:

- gap seconds;
- group-by-source flag;
- window seconds;
- time-filter switch; and
- snake switch.

Do not persist interval IDs, applied bounds, cursor position, or playback
state because they become stale after an import or reload.

### Page and component split

Keep `MapPage.tsx` as the map/layer coordinator. Extract the control surface
to `frontend/src/components/TemporalMapControls.tsx` so the page does not
become one large stateful component.

The controls receive derived intervals and emit explicit events for:

- enabling temporal mode;
- changing the date filter;
- selecting intervals;
- recomputing with new gap/group values;
- applying the selected animation range;
- changing window size or cursor;
- stepping and playing; and
- toggling the snake.

Implement playback in a small hook such as
`frontend/src/useTemporalPlayback.ts`. Use a recursively scheduled one-second
timer, clean it up on unmount and mode changes, and prevent more than one
timer from running. Pause on reload, selection changes, range changes,
manual slider changes, browser-tab hiding, and end-of-range.

## Leaflet Rendering

Use separate Leaflet-owned layers for distinct responsibilities:

- keep the existing marker cluster for canonical points;
- create a temporal marker cluster keyed by `observation_key`; and
- create a non-interactive snake layer group in a pane below markers.

Toggle layers when the master temporal switch changes. Do not destroy the
canonical feed merely to enter temporal mode; returning to the normal map
should be immediate.

Reuse `precisionScore`, `precisionMarkerStyle`, and
`precisionTooltipLabel` for observation markers. Add the UTC observation
time and source file ID to the tooltip. Marker clicks still open the existing
point drawer with `point_id`.

On interval or window changes:

1. derive the visible observation keys;
2. clear and refill only the temporal cluster;
3. derive visible snake segments;
4. clear and refill only the snake layer; and
5. leave the current pan and zoom unchanged.

Fit the map once when temporal data first becomes visible. Never fit on a
playback tick. Reset that one-time fit flag only on an explicit temporal
reload, not on every window.

Draw one `L.polyline` per visible segment because every segment can have a
different ramp color. Set the pane to ignore pointer events, use a line width
close to QGIS's 2 px, and keep lines below markers. No path should connect
the end of one selected interval to the start of another.

## Error and Empty-State Behavior

- If the observation request fails, keep the canonical map usable and show a
  retry action in the temporal card.
- If loading is canceled, retain canonical mode and report the cancellation
  without an error snackbar.
- If there are no timed observations, disable interval, playback, and snake
  controls and explain that canonical points remain available.
- If some observations are untimed, show a non-blocking count explaining
  that temporal mode omits them.
- If date filtering shows no intervals, `Select all` remains a no-op and the
  map shows no temporal markers.
- If one interval has one observation, show its marker but no snake segment.
- If two observations share a timestamp, order by source ID then point ID so
  interval and snake output remains deterministic.
- If a database changes during a paged load, keyset pagination prevents page
  duplication. An explicit reload is the consistency boundary, matching the
  existing map feed.
- Tile failures continue to use the current warning and do not stop temporal
  controls or overlays.

## Test Plan

### Backend tests

Extend `tests/web_test.py` with a `TestMapObservations` class. Use synthetic
fixtures and cover:

- association timestamp preferred over canonical timestamp;
- canonical timestamp used when the association timestamp is null;
- fully untimed associations omitted and counted;
- missing WGS84 coordinates omitted from both timed and untimed map counts;
- two source links for one canonical point returned as two observations;
- precision, source count, and occurrence count serialization;
- UTC serialization of naive SQLite datetimes;
- empty database shape and null bounds;
- composite keyset pagination with no skipped or repeated rows; and
- malformed and negative cursors rejected without exposing SQL details.

No database schema or migration test should change because the endpoint is
read-only and uses existing version-2 tables.

### Pure frontend tests

Add `frontend/tests/temporalMap.test.ts`. Port the important QGIS cases and
cover every branch:

- gap greater than threshold splits;
- gap equal to threshold does not split;
- global and per-source grouping;
- deterministic equal-time ordering;
- inclusive date overlap;
- selected and empty-selected interval behavior;
- no snake across interval gaps;
- single-point intervals create no segment;
- window point inclusion and segment overlap boundaries;
- stepping and clamping at both ends; and
- blue/red ramp endpoints, midpoint, and one-segment behavior.

### Feed and hook tests

Extend `frontend/tests/mapFeed.test.ts` or add
`frontend/tests/temporalMapFeed.test.ts` for:

- multi-page composite cursor accumulation;
- progress metadata from every page;
- cancel during an in-flight request;
- reload discarding a stale page;
- server and generic error formatting; and
- atomic publication only after the final page.

Use fake timers for `useTemporalPlayback` tests. Verify one frame per second,
manual pause, automatic end pause, hidden-tab pause, and timer cleanup.

### Map component tests

Extend the Leaflet stubs in `frontend/tests/MapPage.test.tsx` to record
temporal markers, layer visibility, polylines, and colors. Cover:

- temporal mode is off by default;
- enabling it loads observations and preserves marker click behavior;
- interval selection changes markers without refetching;
- an empty selection removes all temporal markers;
- enabling the window shows only observations in the current frame;
- step and playback update markers and snake without calling `fitBounds`;
- snake toggle adds and removes only the snake layer;
- visible snake colors are recomputed after a step;
- returning to canonical mode restores existing canonical markers; and
- API failure leaves the canonical map usable.

Use accessible names for every switch, date input, interval checkbox, slider,
and transport button. Assert disabled states while data or range is missing.

## Documentation, Packaging, and Verification

Update the `openroland-survey-core` repository, not the QGIS changelog, when the
feature is implemented:

- add the temporal controls, observation semantics, and untimed behavior to
  the Map section in `README.md`;
- add an entry under `## [Unreleased]` in `CHANGELOG.md`;
- document that all temporal calculations are UTC; and
- state that the browser does not depend on QGIS extension tables.

Run formatting first, then the focused tests, then the complete checks:

```text
make delint
python -m pytest tests/web_test.py -q
npm --prefix frontend run lint
npm --prefix frontend run test
npm --prefix frontend run build
make lint
make typecheck
make test
```

After the frontend build passes, replace the packaged static build using the
documented PowerShell workflow and verify the exact build command again:

```powershell
npm --prefix frontend run build
Remove-Item `
    -LiteralPath openroland_survey/static/assets `
    -Recurse `
    -Force `
    -ErrorAction SilentlyContinue
Copy-Item `
    -Path frontend/dist/* `
    -Destination openroland_survey/static/ `
    -Recurse `
    -Force
npm --prefix frontend run build
```

Confirm that stale hashed assets are removed, the new assets are present in
the package manifest, and `GET /map` works through the FastAPI SPA fallback.

QGIS Docker tests are not required for a web-only implementation. If the
QGIS code is later refactored to share fixtures or semantics, run both
`make test-qt5` and `make test-qt6` in this repository.

## Implementation Order

1. Add response schemas, cursor parsing, the observation query, route, and
   backend tests.
2. Add frontend API types and the paged observation feed with cancellation
   tests.
3. Implement and exhaustively test the pure interval, window, and snake
   functions.
4. Add the temporal data and playback hooks.
5. Add `TemporalMapControls` with accessibility and empty states.
6. Integrate temporal marker and snake layers into `MapPage`.
7. Add component tests, optimize window lookup, and verify no refetch occurs
   on local interval settings.
8. Update README and changelog, run all checks, rebuild packaged assets, and
   perform a manual smoke test against a synthetic GeoPackage.

## Acceptance Criteria

The work is complete when all of the following are true:

- The map behaves exactly as it does today until temporal mode is enabled.
- Temporal mode uses point-source observations and the QGIS timestamp
  fallback rule.
- Users can recompute, date-filter, and select intervals without writing to
  the database or refetching observations.
- Users can apply, drag, step, play, and pause a fixed-size UTC window.
- Point visibility follows the selected intervals and optional window.
- The optional snake never crosses intervals and uses the QGIS relative
  blue-to-red ramp for the currently visible segments.
- Untimed data and all empty/error states are explicit and non-destructive.
- Reload and cancellation cannot allow stale pages or timers to update the
  current view.
- Backend, pure logic, feed, playback, and map component branches are covered
  by tests.
- Lint, type checking, Python tests, frontend tests, and the production build
  all pass, and the rebuilt static application is packaged.
