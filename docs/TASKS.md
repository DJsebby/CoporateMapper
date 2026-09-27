# Approved Tasks

This file records tasks explicitly approved by the CEO. A blank template does not authorise work. No development tasks have been approved or added.

## Reusable Task Template

- **Task ID:**
- **Status:**
- **Objective:**
- **Requirements:**
- **Allowed Changes:**
- **Out of Scope:**
- **Notes:**

## Approved Task Entries

### DOCS-003 — Record technology stack and organise documentation

- **Task ID:** DOCS-003
- **Status:** Completed
- **Objective:** Document the CEO-supplied technology stack and organise agent documentation under docs/.
- **Requirements:** Preserve Celery or RQ as an unresolved choice; update document links and current approval status.
- **Allowed Changes:** Move agent instructions and supporting project documents into docs/, retain a root AGENTS.md entry point, and update the README and documentation records.
- **Out of Scope:** Application implementation, dependency installation, and detailed architecture or deployment design.
- **Notes:** Explicitly requested by the CEO on 2026-09-26. See [COMPLETED.md](COMPLETED.md) for the completion record.

### RECON-001 — Google Custom Search name lookup

- **Task ID:** RECON-001
- **Status:** Superseded by RECON-002
- **Objective:** Add a CLI that accepts a full name and company and/or role, queries Google Custom Search, and returns up to 10 structured results.
- **Requirements:** Read `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` from local `.env` or the process environment. Do not make a live query during implementation or tests.
- **Allowed Changes:** `recon/name.py`, focused offline tests, required dependency/configuration, and relevant documentation.
- **Out of Scope:** Fetching result pages, scraping, anti-bot evasion, and additional search sources.
- **Notes:** Explicitly requested on 2026-09-26. See [COMPLETED.md](COMPLETED.md) for verification and limitations.

### RECON-002 — Migrate name lookup to Serper

- **Task ID:** RECON-002
- **Status:** Completed
- **Objective:** Replace Google Custom Search with Serper while preserving the name/context query and top-10 result object.
- **Requirements:** Read `SERPER_API_KEY` from local `.env` or the process environment. Do not make a live search during implementation or tests.
- **Allowed Changes:** `recon/name.py`, focused offline tests, configuration, and relevant documentation.
- **Out of Scope:** Fetching result pages, scraping, and anti-bot evasion.
- **Notes:** Explicitly requested on 2026-09-26. See [COMPLETED.md](COMPLETED.md) for verification and limitations.

### RECON-003 — Simplify Serper request with http.client

- **Task ID:** RECON-003
- **Status:** Completed
- **Objective:** Reduce the Serper lookup to a standard-library HTTP request and a small console runner.
- **Requirements:** Load the key from `.env`, query plain name/company/role terms, request 10 results, and print the raw JSON response. Do not make a live query during implementation.
- **Allowed Changes:** `recon/name.py`, `test_name.py`, and relevant run documentation.
- **Out of Scope:** Scraping result pages and additional search behavior.
- **Notes:** Explicitly requested on 2026-09-26. See [COMPLETED.md](COMPLETED.md) for verification and limitations.

### ENRICHMENT-001 — Australian public professional findings with a shared demo pipeline

- **Status:** Implemented; verification recorded in COMPLETED.md.
- **Objective:** Implement the user-supplied Australian employee aggregation plan and use the same real/demo collection engine with a built-in demo flag.
- **Requirements:** One quoted Serper search per eligible employee/run, seven-day cache, durable accounting, 15 page attempts, explicit Australian work context, identity review, permitted sourced findings, legacy filtering, job controls, live activity, fixture-only Gemini.
- **Allowed Changes:** Extraction/privacy controls, provider/worker and Neo4j job/evidence storage, local API/UI, fixture CLI, configuration, tests and documentation.
- **Out of Scope:** Sensitive dossiers, personal/home contact data, real-employee Gemini calls, scoring, training advice, shared deployment, scheduled monitoring and historical database cleanup.
- **Notes:** Explicit implementation instruction and same-pipeline/demo-flag clarification from the user on 2026-09-27.


### PROFILE-CONTEXT-001 — Click-to-populate employee tables and fictional Gemini context

- **Status:** Implementation in progress; verification will be recorded in COMPLETED.md.
- **Objective:** Populate real employee additional information on explicit click and demonstrate table-to-Gemini context end to end with authored fictional profiles.
- **Requirements:** Preserve real collection exclusions and sourcing; full/partial/minimal demo tables may contain explicitly synthetic personal/sensitive examples. After saving the demo table, generate a sourced profile summary, missing-field gaps and general privacy implications. Persist progress/results and preserve tables on model failure; no automatic request replay.
- **Allowed Changes:** Profile UI, isolated demo catalog/context service, existing worker/API/job persistence, regression tests and documentation.
- **Out of Scope:** Real sensitive-data collection, sending real employees to Gemini, arbitrary fictional overrides, risk scoring, targeting advice and shared deployment.
- **Notes:** Explicit user request and confirmed summary/gaps/privacy preference on 2026-09-27.
