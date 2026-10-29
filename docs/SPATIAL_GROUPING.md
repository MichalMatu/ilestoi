# Spatial indexing for photo markers

The browser creates temporary spatial indexes in `web/map_helpers.js` while it
groups observations. This change does not alter SQLite, the public API, the
user's map settings, or the grouping threshold.

## Behavioral contract

- `groupFieldPhotos` still chooses the **first existing group** within
  `FIELD_PHOTO_GROUP_RADIUS_M` that has the same type and review group kind.
- Vehicle groups still choose the **closest** group within that radius, with
  the earlier created group winning exact distance ties.
- Every accepted photo shifts the group's arithmetic-mean center in exactly
  the previous way. The index updates the group's cell after that movement.
- Pending vehicle photos still attach to the nearest approved group without
  shifting that group's center.
- The existing `metersBetween` function remains the final distance test.

The index's cells restrict which group centers require a distance calculation;
they never decide membership by themselves. The longitude cell width is
conservative for all group-center latitudes within ±84°, given the cosine
factor of the existing distance function. For latitude ≥84° or coordinates
outside the expected longitude interval, the index falls back to the original
scan or includes an overflow group, preserving the existing behavior. The
original distance function does not wrap across the date line, and neither
does the index.

## Performance and limits

The old implementation scans existing groups for every incoming photo,
which can approach O(N²) for spread-out observations. Spatial buckets make
routine sparse lookups depend on nearby groups instead. Worst-case dense
or fallback inputs may still require linear scans; this is **not** a global
time-complexity guarantee.

The Node regression suite compares both old and new grouping semantics for
centroid movement, category and pending separation, nearest matches, boundary
coordinates, deterministic randomized input and a sparse 1600-photo input.
The last case asserts a bounded number of exact distance calculations;
it is not an HTTP or browser-rendering benchmark.

## Release

This change is isolated to JS and this document, with no database migration.
Run `npm run test:web` and `npm run lint:web` in an isolated worktree
before the guarded browser smoke test. Future viewport pagination (prepared
separately by PR #3) and reducing marker re-creation will be needed for
nationwide scale. Keep `main` at the actual accepted production version.
