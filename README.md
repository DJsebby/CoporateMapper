# CorporateMapper

CorporateMapper is a defensive cybersecurity / OSINT platform intended to map an organisation's publicly visible attack surface. Its central **Corporate Surface Map** will show entities and relationships across people, organisational structure, infrastructure, and third parties, helping organisations reduce unnecessary exposure and better protect employees.

## Current status

The [discovery-to-database pipeline](docs/PIPELINE.md), people extractor, local Neo4j connection, and [people map UI](docs/UI.md) with bounded [Australian employee enrichment](docs/ENRICHMENT.md) are available. See the [Neo4j setup walkthrough](docs/NEO4J.md) to start the database and connect crawler output. The [technology stack](docs/ARCHITECTURE.md) is approved. The approved local enrichment version uses one background worker and Neo4j progress. Broader deployment, risk scoring and shared-worker architecture remain outside this implementation; Celery versus RQ remains undecided.

The name-recon utility makes one Serper search API request and prints the response JSON; it does not scrape result pages. Configure `SERPER_API_KEY` in `.env`, install `requirements.txt`, then run `python test_name.py`.

Executable pipeline, database, demo, name-search, manual crawler checks, and `Leaks/` utilities report failures with concise messages and nonzero exit codes. Ctrl+C exits with code 130. Install `requirements.txt` for the declared runtime packages; the optional HIBP browser utility additionally needs Python Playwright and Chromium. Library functions retain their exceptions so callers can distinguish failed work from empty results.

Person image URLs from supported markup are stored with the existing Neo4j evidence and displayed in the UI. The Recent activity box shows actual Neo4j enrichment jobs beside the map. Findings include individual source links and can be dismissed.

## Test with your fictional demo

Stop the API first, then run `.venv/bin/python enrich.py --demo`. This uses the same enrichment engine as real employees, replacing external search/page responses with the built-in demo fixtures. No search credits or Gemini key are needed. Start the API afterward to inspect the saved job and review candidates; tests do not leave a server running. See the [step-by-step guide](docs/ENRICHMENT.md).

Gemini is isolated to `gemini_fixture_eval.py --demo` (mocked) or `--demo --live` (one fictional-fixture request after adding a key). Real collection never invokes Gemini.

## Repository documentation

Agent instructions and supporting project documentation live in `docs/`. The root [AGENTS.md](AGENTS.md) directs agents to the full instructions.

| File | Purpose |
| --- | --- |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent rules, authority, and workflow |
| [docs/CONTEXT.md](docs/CONTEXT.md) | Core product concept and defensive purpose |
| [docs/PIPELINE.md](docs/PIPELINE.md) | Run discovery, prioritisation, crawling, and person storage together |
| [docs/ENRICHMENT.md](docs/ENRICHMENT.md) | Shared demo/real enrichment, limits, sources, review and Gemini fixture tests |
| [docs/DEMO.md](docs/DEMO.md) | Load fictional demo people and delete only that demo |
| [docs/UI.md](docs/UI.md) | Start and use the people map, data interface, and scaling limits |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Testing requirements, acceptance cases, and test commands |
| [docs/TASKS.md](docs/TASKS.md) | Approved tasks and reusable task template |
| [docs/COMPLETED.md](docs/COMPLETED.md) | Completed work and verification log |
| [docs/DECISIONS.md](docs/DECISIONS.md) | CEO-approved decision log |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Approved technology stack and architecture status |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Placeholder for an approved data model |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Placeholder for approved data sources |
| [docs/RISK_MODEL.md](docs/RISK_MODEL.md) | Placeholder for an approved risk model |
| [docs/API.md](docs/API.md) | Placeholder for approved API documentation |
| [docs/SECURITY.md](docs/SECURITY.md) | Placeholder for approved security requirements |
| [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md) | Placeholder for an approved system design |
