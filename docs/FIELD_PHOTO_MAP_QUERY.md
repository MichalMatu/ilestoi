# Public photo map queries (backend, 2026-10-29)

The existing no-argument `GET /api/field-photos` is retained for the current
Leaflet client, with the same `{"status":"ok","photos":[...]}` JSON contract
and the same approval / pending visibility rules. The response remains
unbounded until the frontend is migrated to viewport-based loading.

The server now reads a **projection** of map fields only. It excludes private
EXIF, redactions, originals, owner credentials and unnecessary columns before
materialization. SQL excludes draft and rejected rows; for guests, SQL also
respects enabled photo layers and the independent pending layer switch.
Approved records missing public derivatives are repaired individually using
the existing preparation path. The normal request never writes records.

Optional parameters:

- `bbox=west,south,east,north` in degrees. Inclusive bounds, latitude
  from -90 to 90, longitude from -180 to 180; west > east crosses the date
  line. Invalid, repeated or non-finite bounds give HTTP 400.
- `limit=1..500`: opt-in keyset page size. The response also contains
  `next_cursor` (opaque token or `null`).
- `cursor=<next_cursor>` alongside `limit`: fetch the next page, ordered
  by `created_at DESC, id DESC`. Changing bbox or public layer settings
  between pages may change the result. Do not persist cursors indefinitely.

The unbounded API is deliberately **not** a nationwide-scale delivery
strategy. The next frontend stage must request viewport-filtered pages,
cancel stale requests and render only visible subsets; global counters,
aggregation and clustering will need explicit server contracts. This first
stage prepares safe SQL queries without silently changing current UX.

Release notes: migration 006 adds a sorting index; it is not applied in
production until an explicitly approved release. Local Agent tests run in an
isolated worktree and use synthetic SQLite records, never production data.
