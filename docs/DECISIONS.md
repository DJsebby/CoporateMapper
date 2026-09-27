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

### DEC-002 — Google Custom Search for employee discovery

- **Decision ID:** DEC-002
- **Status:** Withdrawn 2026-09-26. The project team asked that Google Cloud not be used as a collector; the Google collector was removed. CEO confirmed the withdrawal on 2026-09-26 (relayed by the project team).
- **Date:** 2026-09-26
- **Decision:** Employee discovery (COLLECT-001) uses the Google Custom Search JSON API, querying for public LinkedIn profile results. LinkedIn itself is not accessed. All discoverable details are collected, including publicly shown email addresses, phone numbers, and other social/personal profiles.
- **Reason:** CEO selected Google as the search provider and asked that no details be excluded.
- **Approved By:** CEO, approval relayed by the project team on 2026-09-26.
- **Consequences / Constraints:** Requires a Google API key and a Programmable Search Engine ID. Free quota is 100 queries/day and each query returns at most 100 results. Handling rules for collected personal data are not yet defined.

### DEC-003 — LLM and embeddings provider for exposure-assessment extraction

- **Decision ID:** DEC-003
- **Date:** 2026-09-26
- **Decision:** COLLECT-007's structured-fact extraction uses the Anthropic API (via `instructor`) to populate the operational-facts schema from retrieved document passages. Chunk retrieval uses a local FAISS index with local `sentence-transformers` embeddings, not a hosted embeddings API.
- **Reason:** CEO chose Anthropic over OpenAI for the extraction call, and local embeddings over hosted (e.g. LlamaIndex's default OpenAI embeddings) to limit how many third parties see scraped document content from a client's or the org's own site to just the one extraction call.
- **Approved By:** CEO, explicit choice on 2026-09-26.
- **Consequences / Constraints:** Requires `ANTHROPIC_API_KEY` from the environment, read the same way other collectors read API keys (never committed). Adds `instructor`, `anthropic`, `faiss-cpu`, and `sentence-transformers` as dependencies.

### DEC-005 — Automatic .env loading for all crawler CLIs

- **Decision ID:** DEC-005
- **Date:** 2026-09-26
- **Decision:** All crawler CLIs (`crawler/brightdata.py`, `crawler/exposure/cli.py`) load `.env` automatically via `python-dotenv` at startup, instead of requiring the operator to export each key manually every session.
- **Reason:** CEO asked for keys added to `.env` to "just work" every run rather than needing manual export.
- **Approved By:** CEO, explicit request on 2026-09-26.
- **Consequences / Constraints:** Adds `python-dotenv` as a dependency. `.env` remains git-ignored and is never read except by the operator's own machine. `.env` values do not override already-exported environment variables (python-dotenv's default behaviour).
- **Notes:** `DEC-004` is referenced in `crawler/brightdata.py`'s docstring (credit-cap rationale) but was never recorded here; that predates this task and was left as-is.
