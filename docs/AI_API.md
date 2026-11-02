# Generating IleStoi.pl PDF reports from AI tools

The public machine-readable contract is at **`GET /api/ai/openapi.json`**.
It describes a read-only photo search plus one PDF **draft** generation operation. There is
no server-side email transmission, submission to authorities, permanent case record,
public write access to the photo review queue, or bypass of existing moderation.

## Minimal client flow

1. Geocode the user's location (e.g. "Gajowa, Wrocław") using a separate trusted
   geocoding service or map. A street name without a house number may refer to
   multiple locations: narrow down the location instead of silently guessing.
2. `GET /api/field-photos?bbox=west,south,east,north&limit=50`.
   Follow `next_cursor` as needed. Only use approved, active **vehicle**
   photo records. Inspect public photo thumbnails and group coordinates.
3. A car color alone is not reliable identification. If several records match,
   show candidates and have the user select one. Never invent an existing photo ID
   or infer a vehicle's legal status solely from its color or duration of parking.
4. Submit `POST /api/ai/report-pdf` with a JSON object containing the exact
   approved group's photo IDs, actual coordinates, observation time, factual
   vehicle condition and the reporter's explicitly supplied contact details.
   The existing service verifies same-group, approved and active photos,
   coordinate proximity, public image files, size limits and feature switches.
5. Decode `pdf_base64` to `pdf_filename`. Present the draft for human verification.
   Sending it to Straż Miejska is a **separate, explicit action** outside this API.

Example payload (all personal and observation data are placeholders):

```json
{
  "photo_ids": ["EXACT_APPROVED_PHOTO_ID"],
  "lat": "51.000000",
  "lon": "17.000000",
  "reporter_name": "REPLACE_WITH_REAL_NAME",
  "reporter_email": "person@example.invalid",
  "reporter_phone": "REPLACE_WITH_REAL_PHONE",
  "reporter_address": "REPLACE_WITH_REAL_ADDRESS",
  "location_description": "REPLACE_WITH_EXACT_LOCATION",
  "observed_at": "2026-10-28T10:00",
  "vehicle_description": "REPLACE_WITH_VERIFIED_OBSERVATIONS",
  "crop_m": "7.5"
}
```

```bash
curl --fail-with-body -sS --max-time 120 \
  -H 'Content-Type: application/json' \
  --data @report-request.json \
  'https://ilestoi.pl/api/ai/report-pdf' > report-response.json
python3 - <<'PY'
import base64, json
from pathlib import Path
r = json.loads(Path("report-response.json").read_text())
assert r["status"] == "ok"
name = Path(r["pdf_filename"]).name
Path(name).write_bytes(base64.b64decode(r["pdf_base64"], validate=True))
print(name)
PY
```

## Security and operational constraints

- All public generation remains conditional on the `report_pdfs` feature switch
  and existing report rate and concurrency limits.
- Requests are capped by the general JSON body size limit (1 MiB).
- Only public, approved/anonimized photos are copied into the report.
  An AI cannot upload private image bytes through the generator.
- Same-origin checks reject cross-site browser POSTs. Server-to-server clients
  may call the API without a browser Origin header; do not weaken CORS or CSRF
  to accommodate third-party browser scripts.
- No AI authentication credential, identity storage or new privileged action
  is introduced. A client must not interpret a public API as permission to
  send emails or perform mass submissions.
- Cloudflare or network policies can block automated clients independently of
  the backend. Public availability must be checked from the intended client;
  returning HTTP 403 to a bot is not evidence that the backend is down.
- The backend performs no color recognition and has no natural-language street
  search. Those are client-side interpretation/geocoding concerns. Integrations
  should ask for a specific photo/point when uncertain.
- Until a guarded Termux deployment of this change, the new routes are **not**
  available on production: only the older multipart browser generator exists.
