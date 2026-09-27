# People map

The local UI displays people already stored by the extractor in Neo4j. It uses React, TypeScript, Cytoscape.js, and Tailwind, with a local FastAPI service. The UI can create and review bounded enrichment jobs and dismiss individual findings. Use the optional [demo command](DEMO.md) to load fictional people and remove them afterward.

## Start the UI

From the repository root, set up dependencies and build the frontend:

```bash
.venv/bin/python -m pip install -r requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
docker compose up -d
set -a
source .env
set +a
.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Open <http://localhost:8000>. Keep the terminal running; Ctrl+C stops the UI/API but leaves Neo4j running. Build before starting the API so it can serve frontend/dist. See [NEO4J.md](NEO4J.md) if this is a fresh checkout or your database credentials need configuring. Node.js 20.19+ or 22.12+ is needed for the frontend tooling.

For frontend development, keep the API running and use a second terminal:

```bash
npm run dev --prefix frontend
```

Open the Vite URL shown in that terminal (normally <http://localhost:5173>). Requests under /api are proxied to localhost:8000; Neo4j credentials never enter the frontend bundle.

## Use the map

- Choose an organisation, all organisations, or people without a recorded organisation. The first available organisation is selected initially.
- Search all people in that selection by name or position. Use pagination to reach every match; each page shows up to eight people to keep the map readable.
- The map connects people to their recorded organisation. Connections do not represent reporting lines or management hierarchy. All-organisations and unassigned views show person nodes without invented relationships.
- Person cards and details display stored portrait URLs when available, with initials when no usable image exists or an image fails to load. Images are references to their source websites; the application does not download an archive copy. Existing people gain portraits when their supported source pages are crawled again.
- The Recent activity panel sits in a narrow separate box to the left of the organisation map on desktop, and below it on smaller screens. It polls persisted Neo4j enrichment jobs every two seconds, showing source checks, search/page attempts, candidate review and cancellation.
- Every person node shows a name, position, and score of `-`. Extraction confidence is not used as a person score. Missing positions are shown as unavailable.
- Click **View details** to open the person's names, positions, organisations, business contacts, profile links, and typed findings with original source links. Different claims remain visible. Details have a shareable `#person/<identity>` URL and close with Escape or the close button.
- Drag the graph background to pan; use zoom and Fit map controls. Switch to List for easier keyboard navigation. Small screens open in List by default.
- Select up to 20 employees for enrichment. **Enrich selected** reuses eligible seven-day cached searches; **Search again** displays and consumes an additional allowance. Built-in demo runs use the CLI `enrich.py --demo`.
- Refresh reloads database records and never starts a search. An empty database shows an empty state; connection errors show a retry action.

Organisation names are grouped case-insensitively with normalised whitespace, without fuzzy entity resolution. Titles are collected from all of a person's evidence; no claim is made that a particular title belongs to a particular organisation. Outbound links are limited to HTTP/HTTPS; other URL values remain visible as text.

## Data interface

| Endpoint | Result |
| --- | --- |
| GET /api/organisations | Organisation names and distinct person counts; null name denotes unassigned people |
| GET /api/people | Person summaries; optional organisation, unassigned, q, offset, and limit parameters |
| GET /api/people/{identity_key} | Aggregated permitted fields, typed findings and minimized source metadata; 404 when missing |

Person summaries and details include `image_urls`, an ordered list of distinct HTTP(S) image URLs from the person’s evidence (newest evidence first), or an empty list for older records without images. Invalid URLs and URLs containing credentials are excluded from this field; individual findings provide original source links and minimal permitted evidence. Arbitrary raw source JSON is not exposed.

Responses always contain `score: null`; the UI displays `-`. The list limit defaults to 100 and is capped at 200. The UI requests eight summaries at a time; source records load only when opening details. Database failures return a generic 503 response. Enrichment creation/review/cancellation and finding-dismissal write endpoints are documented in [ENRICHMENT.md](ENRICHMENT.md). No shared deployment or employee authentication is included. Run this tool bound to localhost with one API process and without `--reload` or multiple workers.

## Scaling boundary

Graph rendering and network responses are paginated, the Neo4j driver is pooled, and person details use an identity-targeted query. The current extractor stores names and organisations inside JSON evidence. Organisation listing and search therefore still scan that evidence in Python; this is not yet a database-indexed directory for large datasets. Changing the storage model or adding indexes requires a separate approved task.

## Verification

See [REQUIREMENTS.md](REQUIREMENTS.md) for API, browser, and extractor tests. Browser fixtures are fictional and isolated from Neo4j.
