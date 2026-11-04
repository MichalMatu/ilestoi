# IleStoi.pl — UX map shell: implementation checkpoint (2026-11-04)

## Scope and safety

- Working branch: `feature/ux-map-shell-v1`, created from `main` `1f1280b2ba38d3d892b8192b315c4b8f2bb8016c`.
- MacBook Local Agent: `macbook-michal`; isolated source checkout at `~/Library/Application Support/ilestoi-dev/ux-map-shell-v1`.
- This is a **source-only UX candidate**. No production Termux checkout, database, photos, runit service, or Cloudflare routing is modified.
- `main` remains the accepted released branch. Review, physical-device acceptance and a separate guarded deployment are mandatory before promotion.

## Implemented: sprint 1 — map control hierarchy

- `web/partials/app_shell.html`: three independent sections for **Pojazdy**, **Warstwy**, and **Narzędzia**. Existing control IDs and handlers are retained.
- `web/app/ux_map_shell.js`: a small standalone UI state controller for responsive tabs and the expandable mobile bottom sheet. The application map and filter state remain owned by their existing modules.
- `web/styles/ux_map_shell.css`: scoped ergonomic controls, safe-area aware mobile sheet, touch targets, responsive spacing, independent map action buttons.
- On-map **Dodaj zgłoszenie** reuses `openFieldPhotoUploadFromPanel()`, the same public feature gate, and the same location-picking state as the original menu action.
- Public layer toggles, saved filters, the slider/gallery mutually exclusive mode, reports and owner-token workflows retain existing contracts.
- Guided tour switches the appropriate tab before spotlighting a menu control.
- PL/EN translations added; vehicle age filter label now describes observation age, not proven continuous parking.

## Implemented: sprint 2 — desktop nonmodal dock

- Large desktop (`>=1120px`) automatically opens the left sidebar with a 352px map offset; map remains focusable/clickable, backdrop is hidden, and Leaflet size is refreshed.
- Tablet and mobile retain modal menu/focus management, with an accessible bottom sheet below 720px.
- The map panel uses scoped light color tokens; existing complex modals retain their current theme until a separate visual polish review.
- Desktop guided tour and menu focus management were adapted to the persistent, nonmodal dock.
- No new data model, server endpoint or extra frontend framework introduced.

## Verified evidence — Mac Local Agent

- Base before implementation: 102/102 JS tests PASS.
- Candidate at `057b1eae62c5e2b63c40627dd512cfb29d8f8a9f`: `npm run lint:web` PASS.
- `npm run test:web`: **106/106 PASS**.
- `python3 -m unittest discover -s tests -p 'test_*frontend*.py'`: **37/37 PASS**.
- `npm run test:ux:browser`: Chrome headless browser-mode probes **2/2 PASS**:
  - Mobile CSS breakpoint: actual Chrome viewport 500px, 3 tabs switch exclusively, drawer expands and fills bottom width, scrim active.
  - Desktop: viewport 1400px, sidebar 352px, map left offset 352px, scrim disabled, all control groups visible.
  - Browser console exception collector reported no script exceptions in these isolated UI probes.
- Mac isolated source checkout remained clean after the checks. Browser probes use a **mocked local server** and do not represent production API, tiles, upload or report E2E acceptance.

## Deliberately pending

1. Verify responsive behavior on an actual 360–390px smartphone viewport, including safe-area, zoom, touch/scroll and keyboard; Chrome headless min-width gave 500px.
2. Pixel-level visual review against the mockups on Mac Chrome and real Samsung. Light styling for vehicle detail popups, gallery and dialog surfaces still needs review.
3. Redesign selected-vehicle detail view as a contextual card without losing Leaflet popup controls, deep links, edit/report paths, OC status or image anonymization.
4. Redesign the photo upload into explicit steps without changing draft, review, token or privacy semantics.
5. Redesign the admin moderation queue; do not introduce mock fields, automated UFG/CEPiK claims or fictitious upload statuses.
6. Full isolated/backend E2E followed by physical device QA; no release without the documented backup and guarded rollout.

## Commands

```sh
npm ci --prefer-offline --ignore-scripts --no-audit --no-fund
npm run lint:web
npm run test:web
npm run test:ux:browser     # local Chrome/Chromium; optional CHROME_BIN
python3 -m unittest discover -s tests -p 'test_*frontend*.py'
```
