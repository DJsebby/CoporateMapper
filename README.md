# CorporateMapper

CorporateMapper is a defensive cybersecurity / OSINT platform intended to map an organisation's publicly visible attack surface. Its central **Corporate Surface Map** will show entities and relationships across people, organisational structure, infrastructure, and third parties, helping organisations reduce unnecessary exposure and better protect employees.

## Current status

The people extractor, local Neo4j connection, and read-only [people map UI](docs/UI.md) are available. See the [Neo4j setup walkthrough](docs/NEO4J.md) to start the database and connect crawler output. The [technology stack](docs/ARCHITECTURE.md) is approved. Detailed architecture, data models, APIs, collection methods, risk scoring, hosting, and deployment design remain pending CEO approval. Celery versus RQ remains undecided.

The name-recon utility makes one Serper search API request and prints the response JSON; it does not scrape result pages. Configure `SERPER_API_KEY` in `.env`, install `requirements.txt`, then run `python test_name.py`.

## Repository documentation

Agent instructions and supporting project documentation live in `docs/`. The root [AGENTS.md](AGENTS.md) directs agents to the full instructions.

| File | Purpose |
| --- | --- |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent rules, authority, and workflow |
| [docs/CONTEXT.md](docs/CONTEXT.md) | Core product concept and defensive purpose |
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
