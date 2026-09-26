# Completed Work Log

Append completed tasks using the template below. Record actual verification and remaining issues. Templates do not count as completed work.

## Reusable Completed-Work Template

- **Task ID:**
- **Date:**
- **Work Completed:**
- **Files Changed:**
- **Verification:**
- **Decisions:**
- **Remaining Issues:**

## Historical Work

The following entry predates the current setup. Its observations describe that earlier state; current context and instructions supersede them.

## 2026-09-26 — Supporting files for an understanding-focused agent workflow

- Task requested: Read the agent instructions and provide the supporting files needed for an agent-safe workflow focused on understanding.
- Work completed: Read Agents.md and inspected the repository. Added an instruction entry point, verified project context, an understanding-first workflow, a reusable task brief, a decision log, and this completion log.
- Files changed: Added AGENTS.md, PROJECT_CONTEXT.md, WORKFLOW.md, TASK_BRIEF.md, DECISIONS.md, and COMPLETED.md.
- Important decisions: Kept the existing Agents.md intact. Referenced it from AGENTS.md. Marked undocumented product requirements and architecture as unknown rather than choosing them.
- Verification performed: Checked new documents for valid local Markdown links, final newlines, trailing whitespace, and expected file scope. Application tests/builds are unavailable because no application or test configuration exists.
- Remaining issues: Agents.md ends mid-sentence. Product purpose, users, scope, stack, and acceptance criteria still need owner input when relevant to implementation. Documentation guides behavior; it does not enforce tool permissions.

## DOCS-001 — CorporateMapper Repository Documentation Setup

- **Task ID:** DOCS-001
- **Date:** 2026-09-26
- **Work Completed:** Established the CEO-provided CorporateMapper concept and documentation-only workflow, including authority order, approval boundaries, approved-task and decision templates, and unapproved design placeholders. Marked older guidance as superseded while preserving its contents and the previous completion entry. No development tasks or application implementation were added.
- **Files Changed:** Created during this setup across its two stages: CONTEXT.md, TASKS.md, ARCHITECTURE.md, docs/DATA_MODEL.md, docs/DATA_SOURCES.md, docs/RISK_MODEL.md, docs/API.md, docs/SECURITY.md, docs/SYSTEM_DESIGN.md. Modified to finish setup: AGENTS.md, README.md, DECISIONS.md, COMPLETED.md, Agents.md, PROJECT_CONTEXT.md, WORKFLOW.md, TASK_BRIEF.md.
- **Verification:** A Python documentation check confirmed all 13 requested files exist, local Markdown links resolve, required template fields are present, approval placeholders remain explicit, and requested documents have final newlines without trailing whitespace. SHA-256 comparisons against the pre-edit snapshot confirmed only the eight intended existing documents changed in the finishing stage, with no files created or deleted in that stage. No application tests or builds were run because no implementation exists.
- **Decisions:** Applied the CEO's supplied product context, authority order, and scope restrictions. No architecture, technology, data-model, API, collection, or scoring decisions were made. Preserved existing completion history rather than erasing it.
- **Remaining Issues:** Architecture and all detailed implementation/design choices require CEO approval. The next task must be explicitly requested by the CEO.

## DOCS-002 — Remove Superseded Documents

- **Task ID:** DOCS-002
- **Date:** 2026-09-26
- **Work Completed:** Removed the four superseded documents and removed statements in current guidance that they are retained. Earlier completion entries remain as historical records.
- **Files Changed:** Deleted Agents.md, PROJECT_CONTEXT.md, WORKFLOW.md, TASK_BRIEF.md. Updated AGENTS.md, README.md, COMPLETED.md.
- **Verification:** Confirmed all four superseded files are absent, remaining local Markdown links resolve, and current guidance contains no references to the deleted files.
- **Decisions:** CEO explicitly requested removal of redundant documents pointing to replacements.
- **Remaining Issues:** None for this cleanup. Product architecture and implementation remain pending CEO approval.

## DOCS-003 — Record technology stack and organise documentation

- **Task ID:** DOCS-003
- **Date:** 2026-09-26
- **Work Completed:** Recorded the CEO-supplied stack and its approval, keeping Celery or RQ unresolved. Moved agent instructions and supporting project documents into docs/, retained a root agent entry point, and updated links and current scope statements. Preserved historical completion entries.
- **Files Changed:** Moved AGENTS.md, CONTEXT.md, TASKS.md, DECISIONS.md, ARCHITECTURE.md, and COMPLETED.md into docs/. Added a root AGENTS.md entry point. Updated README.md and the moved AGENTS.md, TASKS.md, DECISIONS.md, ARCHITECTURE.md, and COMPLETED.md.
- **Verification:** Checked all local Markdown links, final newlines, and trailing whitespace; git diff --check passed. No application tests or builds apply to this documentation-only repository.
- **Decisions:** Recorded the CEO-approved stack in DEC-001. Organised documentation as requested; retained the root instruction entry point for agent discovery.
- **Remaining Issues:** CEO selection between Celery and RQ is still needed before implementing the task queue. Detailed architecture and implementation remain pending approval.

## EXTRACT-001 — People extractor

- **Task ID:** EXTRACT-001
- **Date:** 2026-09-26
- **Work Completed:** Implemented Extractor(driver, database=None), offline extract(page), and transactional process(page). Extracts explicit Schema.org Person JSON-LD and HTML microdata, resolves document-local references and relative URLs, preserves associated professional/contact fields and source evidence, ranks completeness using the approved confidence weights, and writes Person / PersonEvidence nodes through a caller-owned synchronous Neo4j driver. Uses only standard-library imports plus the existing PageDocument model.
- **Files Changed:** Added extractor.py; appended this entry to docs/COMPLETED.md. crawler/models.py remains unchanged. Temporary tests were kept outside the repository.
- **Verification:** All 11 temporary unittest cases passed: nested JSON-LD graphs and references, URL reference objects and local cycles, exact scoring and stable ordering, microdata scope isolation, itemref and void elements, malformed neighbouring records, conservative identity matching, invalid-page no-write behaviour, repeatable parameterised writes and conflicting evidence, propagated database failures with session closure, and no confidence boost from repetition. git diff --check passed; verified crawler/models.py has no diff. Database interaction was tested with a recording driver double, not a live Neo4j instance.
- **Decisions:** CEO explicitly requested implementation of the supplied plan, authorising this extractor, its 0.60/0.15/0.10/0.10/0.05 confidence weights, and minimal Person / PersonEvidence graph structure. Preserve each claim in JSON evidence; retain maximum confidence on Person nodes. Do not provision databases, install dependencies, or modify other application components.
- **Remaining Issues:** Live Neo4j integration remains unverified without a supplied database. The caller must supply the synchronous driver and available database. Concurrent-write uniqueness requires separately approved database constraints; no migrations or constraints were created.

## NEO4J-001 — Local database and extractor connection

- **Task ID:** NEO4J-001
- **Date:** 2026-09-26
- **Work Completed:** Started Neo4j Community 5.26 using Docker Compose with localhost-only Browser/Bolt ports and a persistent data volume. Generated a private password in ignored .env, installed the official Python driver in ignored .venv, and added a context-managed connection helper that verifies access and supplies the driver to the existing extractor. Added a reproducible setup walkthrough and README link.
- **Files Changed:** Added compose.yaml, .env.example, requirements.txt, database.py, docs/NEO4J.md. Updated README.md and docs/COMPLETED.md. Created local ignored .env and .venv. Existing extractor.py and crawler/models.py were not modified by this task.
- **Verification:** docker compose config --quiet passed; service is running on localhost ports 7474 and 7687. database.py verified live authentication and database access. A synthetic PageDocument passed extraction, live storage, readback, exact confidence assertion, and repeat-write deduplication; only its synthetic records were removed afterward. Confirmed .env and .venv are ignored. git diff --check passed. Installed neo4j driver version 6.3.1.
- **Decisions:** CEO requested a database setup walkthrough and extractor connection, and selected local Docker. Credentials remain local; connection settings use environment variables. Existing person/evidence storage behaviour is preserved.
- **Remaining Issues:** No running crawler implementation exists to supply real PageDocument inputs. Concurrent-write uniqueness constraints remain outside this task. The local database is running and its data persists across container recreation.

## TEST-001 — Extractor regression tests and ongoing testing requirements

- **Task ID:** TEST-001
- **Date:** 2026-09-26
- **Work Completed:** Added 11 permanent offline extractor tests and one opt-in live Neo4j integration test. Documented acceptance cases, test commands, and ongoing requirements to add tests for implementation changes and bug fixes; linked the requirements from agent instructions and README. Completed the previously authorised password recovery using the existing data volume in a temporary network-isolated container. Generated a new password, restored username neo4j in the private .env, and restored normal authenticated service.
- **Files Changed:** Added test_extractor.py and docs/REQUIREMENTS.md. Updated docs/AGENTS.md, README.md, and docs/COMPLETED.md. Updated ignored local .env credentials. No extractor or crawler implementation changes were needed.
- **Verification:** python3 -m unittest -v test_extractor passed 11 offline tests and explicitly skipped the live test. With exported .env credentials, RUN_NEO4J_TESTS=1 .venv/bin/python -m unittest -v test_extractor passed all 12 tests against the running Neo4j database. Tests cover JSON-LD, microdata, normalisation, local references, malformed records, confidence scores/order, identity, parameterised transactions, failure propagation, live persistence, repeat-write deduplication, conflicting evidence, maximum confidence retention, and cleanup of unique synthetic records. The first live run encountered the database restarting; the run after startup passed. Recovery initially encountered isolated-container hostname and system-database readiness-query issues; these were corrected before successful recovery. Verified current credentials authenticate and deliberately incorrect credentials are rejected. Documentation links and git diff --check passed.
- **Decisions:** CEO explicitly approved password recovery and requested test cases plus requirements for tests going forward. Use standard-library unittest with no new test dependencies. Live tests are opt-in and delete only their UUID-scoped fixtures. Recovery followed the Neo4j documented lost-password procedure with networking disabled for the recovery container; the persistent data volume was retained.
- **Remaining Issues:** Tests validate the documented cases, not all possible HTML/JSON-LD or concurrent writes. Concurrent uniqueness constraints remain outside scope. Browser login must use neo4j and the newly generated password stored in local .env; previously exported shell credentials must be reloaded.

## UI-001 — Organisation people map

- **Task ID:** UI-001
- **Date:** 2026-09-26
- **Work Completed:** Built a React/TypeScript/Tailwind interface with a Cytoscape people map, organisation selector, name/position search, eight-person pages, map/list views, zoom/fit controls, responsive layout, and full person details with original evidence. Every score remains a literal dash. Added a read-only FastAPI service over existing Neo4j records; no database model or extractor changes. Built and started the UI/API locally on 127.0.0.1:8000. Added UI startup guidance and ongoing API/browser acceptance requirements.
- **Files Changed:** Created frontend/ (package and lockfile, Vite/TypeScript/Playwright configuration, HTML entry, React components, styles, and browser tests), api.py, test_api.py, requirements-dev.txt, and docs/UI.md. Updated requirements.txt, .gitignore, README.md, docs/REQUIREMENTS.md, and docs/COMPLETED.md. Preserved prior uncommitted testing work in docs/AGENTS.md and test_extractor.py.
- **Verification:** npm run build --prefix frontend passed TypeScript checking and production build. Seven Playwright tests passed for real rendered cards, literal scores, complete details, safe links, Escape/focus restoration, search, pagination, mobile layout, empty/error/retry states, direct links, and refresh after data shrinks; visually inspected a populated fixture screenshot. RUN_NEO4J_TESTS=1 .venv/bin/python -m unittest -v test_api test_extractor passed all 26 tests, including the live extractor-to-API data path and existing live persistence test; synthetic database records were removed. Local HTTP checks returned 200 for the UI, organisations, and people endpoints; live database currently contains zero people. git diff --check passed. The browser connector lacked its Chrome binary, so browser verification used the installed Playwright Chromium instead. TestClient emits an upstream httpx deprecation warning; tests pass.
- **Decisions:** CEO requested a simple UI and explicitly selected actual Neo4j data through read-only FastAPI. Use the approved frontend/backend stack; score stays null in the API and displays as a dash. Organisation links represent recorded membership, not reporting lines. Show eight records per page for readable nodes and default narrow screens to the equivalent list. Keep credentials on the backend and bind the local service to localhost.
- **Remaining Issues:** Organisation filtering/search currently scans existing JSON evidence in Python; pagination bounds response and rendering size but does not make database scans indexed. Larger-scale storage/index changes require a separate task. No real people currently exist in Neo4j; the empty state will remain until extraction supplies records. No scoring, database schema, deployment, or authentication changes were made.

## DEMO-001 — Fictional demo data with scoped cleanup

- **Task ID:** DEMO-001
- **Date:** 2026-09-26
- **Work Completed:** Added demo.py to seed 17 fictional people through the existing extractor's parsing and confidence logic, with deterministic IDs/timestamps and explicit demo_dataset ownership metadata on created nodes and relationships. Added --delete to remove only matching owned demo records in one transaction, without broad deletion or deleting unrelated relationships. Included two labelled demo organisations, a shared advisor, one unassigned person, missing-position coverage, contacts, and full evidence. Loaded the default demo for UI testing.
- **Files Changed:** Created demo.py, test_demo.py, and docs/DEMO.md. Updated README.md, docs/UI.md, docs/REQUIREMENTS.md, and docs/COMPLETED.md. No extractor, API, frontend, dependency, or database constraint changes.
- **Verification:** RUN_NEO4J_TESTS=1 .venv/bin/python -m unittest -v test_demo test_extractor test_api passed all 34 cases, including eight new demo tests. Live cleanup tests preserve unrelated people, non-demo evidence attached to demo people, shared evidence, edited demo evidence, and unowned ID collisions. Exercised the actual CLI sequence seed, seed, --delete, seed: repeated seeding did not duplicate records; cleanup removed 17 people and 17 evidence records; 17 people were then restored. Verified through the UI API that demo organisation counts are 12 and five (one shared person), scores stay null, and full details are available. Existing TestClient/httpx deprecation warning remains non-failing. git diff --check passed.
- **Decisions:** CEO requested demo database data and a flag deleting only that data. Cleanup requires explicit ownership plus exact IDs, preserves changed evidence and nodes with other links, and refuses to claim unmarked collisions. Keep demo version-one fixture identity and timestamps stable; any future revision needs distinct versioning and cleanup support.
- **Remaining Issues:** Seed and cleanup commands should run sequentially because concurrent uniqueness constraints remain outside scope. Cleanup deliberately retains records with additional links or modified evidence and reports them rather than deleting potentially unrelated data. Demo is left loaded for user testing; run demo.py --delete and refresh the UI to remove it.
