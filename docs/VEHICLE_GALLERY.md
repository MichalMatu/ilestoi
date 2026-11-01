# Vehicle gallery and bottom dock

Candidate feature branch: `feature/wreck-gallery-bottom-dock`.

- The existing map-source slider remains unchanged in its original HTML and CSS.
- The optional bottom dock has **map / gallery / none** modes, remembered in localStorage. When gallery is open, the original slider hides and compact accessible map-source dots take its place.
- The menu has a per-browser gallery toggle; an admin public-feature toggle can hide the public gallery entirely.
- An admin sees a small star overlay in the **top-right corner of each approved vehicle thumbnail** without adding rows or changing its grid. Selecting a priority (0 off; 1 featured; 2 high; 3 urgent) chooses exactly that photo as the group cover. Only approved active vehicles are eligible.
- The SQLite field `field_photos.vehicle_gallery_priority` is changed by the existing admin photo-review PATCH route. Selecting one photo clears nomination of its group peers within the existing spatial radius. Marking a group removed clears its nomination.
- `GET /api/field-photos/gallery?bbox=west,south,east,north` returns up to 100 approved active nominated photo summaries from a read-only indexed query. The browser deduplicates close locations and displays at most ten in the currently loaded area.
- Selecting a thumbnail focuses the existing marker and popup; no separate case entity or unreviewed originals are exposed.
- Test on an isolated Termux worktree before any guarded production migration/release. Keep production `main` at its deployed SHA.

Known limitation: current grouping is spatial (1 m) and depends on observed photo positions. This feature intentionally reuses that model rather than creating persistent vehicle entities.
