# Approved Decision Log

Record only decisions explicitly approved by the CEO. A template is not a decision or approval. Approved decisions are recorded below.

## Reusable Decision Template

- **Decision ID:**
- **Date:**
- **Decision:**
- **Reason:**
- **Approved By:**
- **Consequences / Constraints:**

## Approved Decisions

### DEC-001 — Technology stack

- **Decision ID:** DEC-001
- **Date:** 2026-09-26
- **Decision:** Backend: Python, FastAPI, Pydantic, Celery or RQ, Redis. Databases: PostgreSQL, Neo4j. Frontend: React, TypeScript, Cytoscape.js, Tailwind. Infrastructure: Docker, Docker Compose.
- **Reason:** CEO supplied this technology stack and requested it be added to repository documentation.
- **Approved By:** CEO, explicit request dated 2026-09-26.
- **Consequences / Constraints:** Celery versus RQ remains undecided. This approval records the stack only; detailed architecture, implementation, dependency installation, and deployment are not authorised by this documentation task.

### DEC-002 — Google Custom Search for name reconnaissance

- **Decision ID:** DEC-002
- **Date:** 2026-09-26
- **Decision:** Use the Google Custom Search JSON API for an explicitly invoked, single-query lookup of a supplied full name with company and/or role context. Return at most 10 API-provided title, URL, and snippet records.
- **Reason:** The CEO requested a name lookup script and confirmed existing API access.
- **Approved By:** CEO, explicit request dated 2026-09-26.
- **Consequences / Constraints:** Do not fetch result pages or add bot-detection evasion. Keep credentials in local environment configuration. No live query is authorized during implementation or tests. Google's API is closed to new customers and existing access ends January 1, 2027.

### DEC-003 — Serper for name reconnaissance

- **Decision ID:** DEC-003
- **Date:** 2026-09-26
- **Decision:** Replace Google Custom Search with Serper's Google Search API for the name-recon utility. Send one query and return at most 10 API-provided title, URL, and snippet records.
- **Reason:** The CEO requested migration because Google Custom Search does not work for this use.
- **Approved By:** CEO, explicit request dated 2026-09-26.
- **Consequences / Constraints:** Use `SERPER_API_KEY` from local environment configuration and send it in `X-API-KEY`. Do not fetch result pages or add anti-bot evasion. No live search is authorized during implementation or tests. This supersedes DEC-002 for the name-recon utility.

### DEC-004 — Standard-library HTTP client for the manual lookup

- **Decision ID:** DEC-004
- **Date:** 2026-09-26
- **Decision:** Use Python's `http.client` for the one-off Serper lookup and print the raw JSON response.
- **Reason:** The CEO requested the smallest Python equivalent of the supplied HTTP client example.
- **Approved By:** CEO, explicit request dated 2026-09-26.
- **Consequences / Constraints:** Preserve the plain name/company/role query, top-10 request, and local `SERPER_API_KEY`; do not execute live searches during implementation.
