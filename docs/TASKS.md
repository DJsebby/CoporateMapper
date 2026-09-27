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
