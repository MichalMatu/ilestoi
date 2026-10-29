# Viewport-based field photo loading

This is a **follow-up to PR #3**, which provides `bbox`, `limit` and
`next_cursor` on `GET /api/field-photos`. Do not release the frontend
without that backend contract. No standalone feature flag or compatibility
fallback hides a missing endpoint.

After admin-session bootstrap, the browser requests a rectangular area around
the currently visible Leaflet viewport (12.5% padding per side), with pages of
500. Requests are canceled on later viewport changes and superseded results
never replace the map. A 250-ms map-movement debounce avoids sending a request
for each drag frame. Data are committed to the marker layers **only once all
pages have completed**. Explicit refresh after upload, moderation, position
change and owner deletion still fetches fresh data.

The requested area is clamped to valid latitudes; longitudes are normalized
across the international date line. A viewport spanning at least 360 degrees
uses the complete -180..180 interval. A repeated or malformed server cursor,
an overfull page or more than 40 pages is treated as an error instead of
displaying a silently incomplete map. The old unbounded client request is
removed; the backend keeps an unbounded API for older deployed clients.

**Counts and filters are now local to the map area** (including its padded
margin), not national totals. Count tooltips in both languages say so. This
change does not provide countrywide aggregate counts or server-side clusters:
wide zoom levels can still require many pages, and marker construction may
still become costly. A future dedicated cluster/summary endpoint should
handle truly national-scale overview levels.

QA must cover pagination, invalid/repeating cursors, abort and stale responses,
dateline/full-world bounds, and a real-browser viewport pan, before release.
