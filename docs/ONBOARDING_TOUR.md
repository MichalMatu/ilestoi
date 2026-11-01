# First-visit guided tour (IleStoi)

The interactive product tour is implemented in native JavaScript in
`web/app/onboarding_tour.js`. It deliberately does **not** depend on Driver.js
or another external CDN: the site is a script-ordered, non-bundled frontend.
Styles live in `web/styles/onboarding_tour.css` and markup in
`web/partials/onboarding_tour.html`. Translations are provided in Polish and
English using the existing `t(...)` dictionaries.

## User flow

The tour normally appears after the initial data load unless the user has seen the separate first-visit visual introduction
(or its error state). A versioned local-storage flag
`ilestoi-onboarding-v1-complete` records **Finish** or **Skip**; the first
loading attempt does not count as completion. Existing visitors are unaffected
when they have already completed this version. It can be replayed from
**Menu → Samouczek / Guided tour**. Photo deep links are intentionally not
interrupted.

Steps:

1. Welcome with Finish/Skip options.
2. Actual vehicle marker (or a map explanation if there are no approved pins).
3. Actual Leaflet popup with vehicle photos/details (only if a marker exists).
4. Actual popup PDF-report action (when enabled) or the popup itself.
5. Existing Add photo control (or explanation if submissions are unavailable).
6. Actual vehicle layer/filter group.
7. Existing basemap selection.
8. Completion and replay instructions.

The walkthrough may temporarily pan the map and open a real **read-only**
vehicle popup. It restores the user's previous map view and popup afterward,
and does not submit reports, select a file, modify filters, or change server data.

The tooltip automatically repositions around real targets; a full-screen
interaction blocker prevents accidental activation of highlighted controls.
The tour is a labelled modal dialog, traps keyboard focus, handles Escape, and
adapts to narrow/short viewports. The app's existing accessibility isolation
makes the active tour and, where relevant, the open menu reachable to assistive
technology. During the tour, Next, Back and Skip remain accessible.

## Tests and release

Run:

```sh
node --test tests/js/onboarding_tour.test.mjs
python3 -m unittest discover -s tests -p 'test_onboarding_tour_frontend.py'
npm run lint:web
npm run test:web
```

Before release, perform a browser walkthrough at desktop/mobile sizes,
including empty map, unavailable photo upload, keyboard Tab/Shift-Tab/Escape,
PL/EN, popup report enabled/disabled, first visit and replay.

Keep work on short-lived feature branches from `main`; production `main`
is release-only as specified by AGENTS.md.

## First-visit visual introduction

The separate `web/intro.html` contains the 13.6-second four-scene responsive visual story. `web/app/intro_overlay.js` mounts it on a first ordinary visit to the homepage, not for deep links. A versioned storage flag `ilestoi-intro-v1-seen` records completion or skip; playback never writes application data. The same-origin parent checks origin and iframe sender before closing. After playback the embedded intro closes automatically; it is also replayable from the menu.

The visual story replaces the automatic full guided tour for people who have seen the intro. The interactive map tour remains manually available in the menu. A single document uses portrait layout for phones and portrait tablets, landscape layout for desktops and landscape tablets.
