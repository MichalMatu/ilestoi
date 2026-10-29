# Public photo map queries (backend, 2026-10-29)

The no-argument `GET /api/field-photos` remains available for older
clients, with the same `{"status":"ok","photos":[...]}` JSON contract
and the same approval / pending visibility rules. The current frontend
requests viewport pages at detail zoom (or for admin/direct links/advanced
filters) and bounded photo-count aggregates at overview zoom.

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
strategy. Viewport pagination, stale-request cancellation and bounded
16×16 server-side aggregation are now integrated in release candidate PR #9.
Overview counters represent photos rather than vehicle groups.
The legacy endpoint stays available for previously deployed clients.

Release notes: migration 006 adds a sorting index; it is not applied in
production until an explicitly approved release. Local Agent tests run in an
isolated worktree and use synthetic SQLite records, never production data.
