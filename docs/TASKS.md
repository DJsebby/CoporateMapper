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

### COLLECT-001 — Search-engine-based employee discovery

- **Task ID:** COLLECT-001
- **Status:** Completed; Google collector removed 2026-09-26 at project team request (Google Cloud not to be used as a collector). Shared models and helpers retained in `crawler/people_search.py`.
- **Objective:** Discover publicly listed people associated with a target organisation, and their details, using Google search results for LinkedIn profiles, without connecting to LinkedIn directly.
- **Requirements:**
  - Input: company name, optional aliases, optional company email domain, and a result limit.
  - Query the Google Custom Search JSON API with an engine restricted to `linkedin.com/in`, e.g. `site:linkedin.com/in "<Company>"`.
  - Extract from result titles, snippets, and page metadata: name, job title, department and seniority (inferred from title by keyword rules), location, profile URL, and any publicly shown email addresses, phone numbers, and other social/personal profiles.
  - Run additional Google queries for published contact patterns such as `"@<domain>"`.
  - Record provenance for every detail (query, result URL, timestamp) and mark each as observed or inferred.
  - De-duplicate people by profile URL and by name plus company.
  - Read the API key and engine ID from environment variables; respect Google limits (100 free queries/day, maximum 100 results per query).
  - Return Pydantic models, per DEC-001.
  - Unit tests against saved sample Google responses, with no network calls.
- **Allowed Changes:** New people-discovery module under `crawler/` and its tests; Pydantic and HTTP client (`httpx`) dependencies; entries in DATA_SOURCES.md, DECISIONS.md, and COMPLETED.md.
- **Out of Scope:** Logging into or directly scraping LinkedIn, visiting profile pages, risk scoring, database persistence, API endpoints, and frontend.
- **Notes:** Approved by the CEO on 2026-09-26, relayed by the project team. The CEO should define handling rules for collected personal contact data (authorised targets, retention) in SECURITY.md.

### COLLECT-003 — Bright Data employee discovery and enrichment

- **Task ID:** COLLECT-003
- **Status:** Superseded by COLLECT-005 for discovery; enrichment code retained
- **Objective:** Discover a target organisation's employees and their details using Bright Data's LinkedIn data, replacing the withdrawn Google collector.
- **Requirements:** Input company LinkedIn URL or name, optional email domain, and record limit. Collect name, job title, work history, location, education, profile URL, linked profiles, and any shown emails/phones. Infer department and seniority with the existing rules. Record Bright Data provenance; de-duplicate by profile URL. Default 25 records per run, hard maximum 200. API key from `BRIGHTDATA_API_KEY`. Offline tests on saved sample responses.
- **Allowed Changes:** New module under `crawler/` and tests; entries in DATA_SOURCES.md, DECISIONS.md, SECURITY.md, and COMPLETED.md; `.gitignore` entry for collected output.
- **Out of Scope:** Google or any Google Cloud service, browser automation, persistence, API endpoints, and frontend.
- **Notes:** Approved by the CEO on 2026-09-26 (relayed). Bright Data account has no payment card; stay within the 5,000 free records/month. Bright Data's LinkedIn profile scraper discovers by name or enriches known profile URLs; it cannot list a company's employees, so the discovery input is pending a team decision.

### COLLECT-004 — Apollo executive exposure report

- **Task ID:** COLLECT-004
- **Status:** Approved; not started
- **Objective:** Demonstrate leadership exposure to whaling by reporting what Apollo reveals about the target's executives.
- **Requirements:** Find owner/founder/C-suite/VP/head/director staff for the company domain. Enrich emails by default (1 credit each); phone lookups (8 credits each) only with an explicit option. Hard credit cap per run with a cost preview before spending. Per-executive exposure details and an organisation summary. `--replay` mode to present saved results without API calls. API key from `APOLLO_API_KEY` (each team member's own). Offline tests on saved sample responses.
- **Allowed Changes:** New module under `crawler/` and tests; entries in DATA_SOURCES.md, DECISIONS.md, and COMPLETED.md.
- **Out of Scope:** Writing or sending phishing messages, spending credits on non-executives, persistence, API endpoints, and frontend.
- **Notes:** Approved by the CEO on 2026-09-26 (relayed). Team has four members, each with an Apollo allowance.

### COLLECT-005 — Website-seeded employee discovery with LinkedIn expansion

- **Task ID:** COLLECT-005
- **Status:** Approved; in progress
- **Objective:** Discover a target organisation's employees without search engines: seed from people named on the organisation's own website, then expand through related LinkedIn profiles returned by Bright Data.
- **Requirements:**
  1. Seed: fetch user-specified pages of the target's website; extract names, titles, and any LinkedIn profile links. No Bright Data credits.
  2. Resolve: find LinkedIn profiles for seed names without links using Bright Data's name-based discovery.
  3. Enrich: fetch full profiles, including `connections`, `people_also_viewed`, and `similar_profiles`.
  4. Expand: collect candidates from related-profile lists; keep only those whose profile lists the target as current employer.
  5. Prioritise: order candidates by the number of distinct confirmed employees that listed them, then by connections count ("500+" treated as at least 500).
  6. Stop after 3 expansion rounds, on reaching the record cap (default 25, maximum 200), or when a round finds no new employees.
  7. Output existing `Person` records with provenance, plus how each person was found (website, or via which employees).
  8. Offline tests using saved sample responses with fictional people.
- **Allowed Changes:** New and updated modules under `crawler/` and tests; entries in DATA_SOURCES.md, DECISIONS.md, and COMPLETED.md.
- **Out of Scope:** LinkedIn login, collecting connection lists, search engines, Apollo, persistence, API endpoints, and frontend.
- **Notes:** Approved by the CEO on 2026-09-26 (relayed). Replaces COLLECT-003's search-engine discovery, which live testing showed was unreliable (Bing ignored `site:`; Google returned unrelated profiles; the profiles dataset rejected discovery by company). Reuses COLLECT-003's enrichment code.

### COLLECT-006 — Domain and infrastructure discovery

- **Task ID:** COLLECT-006
- **Status:** Completed
- **Objective:** Map a target organisation's public domains and infrastructure footprint from its own website and public DNS/certificate records.
- **Requirements:**
  - Input: the organisation's primary domain(s).
  - Enumerate subdomains via certificate transparency logs (crt.sh) and public DNS records (A, MX, TXT, NS, CNAME).
  - Identify hosting/CDN providers from DNS and IP ownership (WHOIS/ASN lookup).
  - Detect public technologies from the website itself (server headers, common JS libraries, CMS fingerprints); no login, no scraping behind auth.
  - Record SPF/DMARC presence without deriving individual employee email addresses.
  - Output structured records with provenance per finding.
  - Offline tests using saved sample DNS/crt.sh/HTTP responses.
- **Allowed Changes:** New module under `crawler/`, tests, entries in DATA_SOURCES.md, DECISIONS.md, COMPLETED.md.
- **Out of Scope:** Port scanning, vulnerability scanning, active exploitation, anything requiring credentials, and any per-employee data collection.
- **Notes:** Approved by the CEO on 2026-09-26 (relayed).

### COLLECT-007 — Public-document exposure assessment

- **Task ID:** COLLECT-007
- **Status:** Completed; live-tested against ahcsa.org.au
- **Objective:** For a single, explicitly authorised target domain, discover public documents (policy PDFs, annual/ESG reports, careers pages, ToS, whitepapers, help-centre articles), extract operational facts with quote-level provenance, and produce a defensive exposure report of what those disclosures enable for pretexting/phishing, with remediation notes.
- **Requirements:**
  1. **Authorisation gate:** refuse to run against a domain unless the operator explicitly asserts authorisation for that exact domain (e.g. a required CLI flag/argument naming the domain plus a confirmation flag); abort with a clear error otherwise. No default-on or implied authorisation.
  2. **Discovery:** given the authorised domain, find candidate document URLs via sitemap.xml and same-domain link crawling only (no third-party search engines, per DEC-002's withdrawal). Respect robots.txt; rate-limit requests; identify the crawler in the User-Agent string.
  3. **Fetch & normalise:** download PDF (via pymupdf), DOCX (via python-docx), and HTML (existing HTTP conventions); extract clean text with page/section metadata retained for provenance.
  4. **Chunk & index:** split normalised text into passages and build a local FAISS index using local sentence-transformers embeddings (DEC-003) — no embedding content leaves the machine.
  5. **Structured extraction:** a Pydantic schema of operational facts (`remote_policy`, `device_policy`, `headcount_band`, `office_locations`, `primary_vendors_tooling`, `key_named_staff`, `support_contact_patterns`), each field allowing `not_stated`. Populate it via `instructor` against the Anthropic API (DEC-003) over retrieved passages only, not whole documents.
  6. **Provenance & confidence:** every populated field records a source URL, a verbatim supporting quote, and a confidence flag. No fact without a source.
  7. **Exposure report:** aggregate into one entity record; generate a defensive summary of which disclosed facts most plausibly enable pretexting (e.g. named vendors -> vendor-impersonation lures), with remediation notes. Output both JSON and a Markdown report.
  8. Cap documents fetched per run (default 40, hard maximum 150).
  9. Offline tests using saved sample HTML/PDF fixtures and a stubbed extraction client; no live network or live LLM calls in tests.
- **Allowed Changes:** New module(s) under `crawler/` (e.g. a package for discovery, fetch/normalise, indexing, schema, extraction, and reporting) and their tests/fixtures; add `pymupdf`, `python-docx`, `beautifulsoup4`, `faiss-cpu`, `sentence-transformers`, `instructor`, and `anthropic` to `crawler/requirements.txt`; entries in DATA_SOURCES.md, DECISIONS.md, SECURITY.md, and COMPLETED.md; `.gitignore` entries for any local document cache or index files.
- **Out of Scope:** Running without explicit per-domain authorisation; contacting any domain other than the one asserted as authorised; bypassing robots.txt; login-gated or paywalled content; search engines; database persistence; API endpoints; frontend; sending document content to any third party other than the approved Anthropic extraction call.
- **Notes:** Approved by the CEO on 2026-09-26. Extraction LLM (Anthropic) and embeddings (local FAISS + sentence-transformers) selected per DEC-003 to avoid sending scraped document content to more than one third party.
