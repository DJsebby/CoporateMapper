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

## COLLECT-001 — Search-engine-based employee discovery

- **Task ID:** COLLECT-001
- **Date:** 2026-09-26
- **Work Completed:** Added a Google Custom Search collector that finds people associated with a target organisation from public LinkedIn profile results, without requesting linkedin.com. It extracts name, job title, location, profile URL, emails, phone numbers, and other social profile links; infers department and seniority from job titles; records provenance (query, result URL, timestamp) and observed/inferred status for every detail; de-duplicates by profile URL and by name plus company; and collects organisation-level emails/phones from a `"@<domain>"` query. Includes a request budget, request throttling, and a CLI that outputs JSON.
- **Files Changed:** Created crawler/people_search.py, crawler/__init__.py, crawler/requirements.txt, crawler/tests/__init__.py, crawler/tests/test_people_search.py, crawler/tests/fixtures/google_linkedin_acme.json. Updated docs/TASKS.md, docs/DECISIONS.md (DEC-002), docs/DATA_SOURCES.md, docs/COMPLETED.md.
- **Verification:** `python -m unittest discover -s crawler/tests -t .` ran 26 tests, all passing, using a fictional saved Google response and httpx mock transport (no network). CLI exits with a clear error when credentials are missing. `git diff --check` passed. Not verified against the live Google API because no API key or engine ID was available.
- **Decisions:** Recorded DEC-002 (Google Custom Search; collect all discoverable details). API key sent in the `X-goog-api-key` header so it does not appear in URLs or logs. Dependencies pinned as `pydantic>=2.7,<3` and `httpx>=0.27,<1`; tested with pydantic 2.13.5 and httpx 0.28.1 on Python 3.10.
- **Remaining Issues:** Live API run needed once credentials exist. Title parsing and department/seniority rules are heuristic and may need tuning on real results. Personal-data handling rules (authorised targets, retention) still need CEO definition in SECURITY.md. README.md and docs/AGENTS.md still describe the repository as documentation-only; updating them was outside this task's allowed changes.

## COLLECT-001 follow-up — Remove Google collector

- **Task ID:** COLLECT-001 (follow-up)
- **Date:** 2026-09-26
- **Work Completed:** Removed the Google Custom Search client, collector, and CLI at the project team's request that Google Cloud not be used as a collector. Kept the shared Person/Detail models, LinkedIn title and contact extraction helpers, department/seniority classification, and the merge helper for reuse by future collectors. Also removed the abandoned COLLECT-002 (Playwright) task, decision, data-source entry, requirement, and `.gitignore` entry; no Playwright code had been written.
- **Files Changed:** Updated crawler/people_search.py, crawler/tests/test_people_search.py, docs/TASKS.md, docs/DECISIONS.md, docs/DATA_SOURCES.md, docs/COMPLETED.md. Deleted crawler/tests/fixtures/google_linkedin_acme.json.
- **Verification:** `python -m unittest discover -s crawler/tests -t .` ran 12 tests, all passing. Confirmed no Google or Playwright references remain in code, requirements, or current-source docs.
- **Decisions:** DEC-002 marked withdrawn. `httpx` kept in crawler/requirements.txt for the proposed Bright Data and Apollo API collectors.
- **Remaining Issues:** CEO confirmation of the DEC-002 withdrawal. Bright Data discovery/enrichment and the Apollo executive exposure report await CEO approval. `Person.matched_in` values ("title"/"snippet") are search-specific and will need revisiting for Bright Data records.

## COLLECT-006 — Domain and infrastructure discovery

- **Task ID:** COLLECT-006
- **Date:** 2026-09-26
- **Work Completed:** Built a domain/infrastructure collector: subdomain discovery via crt.sh certificate transparency; DNS records (A, MX, TXT, NS) for the apex domain plus A-record resolution for discovered subdomains (capped, default 25, to bound DNS load); hosting/CDN/DNS/email-provider identification from DNS record patterns and RDAP IP-registrant lookups; public technology detection from homepage headers and content (CMS, framework, analytics, CDN); SPF and DMARC presence and policy. Every finding records its source and retrieval time. No login, no port scanning, no personal data collected.
- **Files Changed:** Created crawler/infra.py, crawler/tests/test_infra.py, crawler/tests/fixtures/crtsh_acme.json, crawler/tests/fixtures/infra_homepage.html, crawler/tests/fixtures/rdap_ip.json. Updated crawler/requirements.txt (dnspython), docs/TASKS.md, docs/DATA_SOURCES.md, docs/COMPLETED.md.
- **Verification:** `python -m unittest discover -s crawler/tests -t .` ran 52 tests, all passing, using fictional saved DNS/crt.sh/HTTP/RDAP responses (no network). Also ran a live check against `example.com` (the IANA domain reserved for this kind of testing, chosen instead of scanning an unrelated real company) — correctly found 6 subdomains, real Cloudflare hosting/DNS providers via both DNS-pattern and RDAP lookups, and correct SPF (`v=spf1 -all`, present) and DMARC (`p=reject`, present) records. That live run caught two real bugs, both fixed and covered by a new regression test: dnspython's TXT records carry literal wire-format quote characters, which silently broke SPF/DMARC detection; and MX record string conversion left a stray trailing space on null-MX records.
- **Decisions:** None beyond the approved task scope.
- **Remaining Issues:** RDAP lookups are made per resolved IP with no caching or rate limiting; on a domain with many subdomains resolving to few distinct IPs this is fine, but a domain with many distinct IPs could make many RDAP calls per run. Provider and technology pattern lists are illustrative, not exhaustive, and will likely need extending as real targets are tested.

## COLLECT-006 follow-up — URL input handling and DMARC validity check

- **Task ID:** COLLECT-006 (follow-up)
- **Date:** 2026-09-26
- **Work Completed:** Fixed two issues found running the collector against a real target (ahcsa.org.au) at the CEO's request. (1) The CLI only accepted a bare domain; passing a full URL silently produced garbage DNS lookups. It now accepts a bare domain, a domain with a path, or a full URL. (2) The live run surfaced a genuine DMARC misconfiguration: one TXT record whose content embeds two separate "v=DMARC1" statements (likely from two tools each appending their own directive). The collector was reporting this as a normal present record; per RFC 7489 a record with more than one "v=DMARC1" tag is invalid and mail receivers are expected to disregard it entirely. Added a `note` field to flag this (and the equivalent SPF case) rather than silently reporting a misleading "present" result.
- **Files Changed:** Updated crawler/infra.py, crawler/tests/test_infra.py.
- **Verification:** `python -m unittest discover -s crawler/tests -t .` ran 58 tests, all passing, including new regression tests for URL-input normalization and the duplicate-DMARC-tag case. Re-ran live against ahcsa.org.au (a real target the CEO pointed at, not one I chose) after each fix: the original URL form now works, and the DMARC finding now correctly carries a note explaining why it will likely be disregarded by mail receivers despite technically being present.
- **Decisions:** None beyond the approved task scope; this is a correctness fix, not a scope change.
- **Remaining Issues:** Same as previously recorded (RDAP calls are not rate-limited or cached; a run against ahcsa.org.au hit a 429 from rdap.org on one lookup, which was handled gracefully by returning no provider for that IP rather than failing the run).

## COLLECT-007 — Public-document exposure assessment

- **Task ID:** COLLECT-007
- **Date:** 2026-09-26
- **Work Completed:** Built the public-document exposure-assessment pipeline: an authorisation gate that refuses to run unless the operator asserts the exact target domain; sitemap/homepage-link discovery restricted to that domain and robots.txt-compliant, with a custom User-Agent and rate limiting; PDF (pymupdf)/DOCX (python-docx)/HTML fetch and normalisation with per-section location metadata; text chunking and a local FAISS index over local sentence-transformers embeddings (nothing sent to a hosted embeddings API); a Pydantic `OperationalFacts` schema (every field allows `not_stated`) populated via `instructor` against the Anthropic API over retrieved passages only, with quote/source_url/confidence on every populated fact; a deterministic (non-LLM) rule set mapping disclosed facts to pretexting/phishing risks with remediation notes; JSON and Markdown report output; and an end-to-end CLI (`python -m crawler.exposure.cli`).
- **Files Changed:** Added crawler/exposure/__init__.py, authorization.py, discovery.py, fetch.py, index.py, schema.py, extract.py, report.py, cli.py; added crawler/tests/test_exposure_authorization.py, test_exposure_discovery.py, test_exposure_fetch.py, test_exposure_index.py, test_exposure_extract.py, test_exposure_report.py, test_exposure_cli.py. Updated crawler/requirements.txt (pymupdf, python-docx, faiss-cpu, sentence-transformers, instructor, anthropic), .env.example (ANTHROPIC_API_KEY), .gitignore (exposure cache directory), docs/TASKS.md, docs/DECISIONS.md (DEC-003), docs/SECURITY.md, docs/DATA_SOURCES.md.
- **Verification:** Installed the new dependencies into the project's `.venv` and ran `python -m unittest discover -s crawler/tests`: 100 tests pass (58 pre-existing plus 42 new), all offline — no live network or LLM calls; the HTTP client, FAISS/embedder, and instructor/Anthropic client are all dependency-injected fakes in tests. Manually ran the CLI to confirm it refuses to proceed both with `--authorized-domain` missing and with a mismatched `--authorized-domain`, in each case before any network request is made.
- **Decisions:** CEO chose the Anthropic API for structured extraction and local FAISS + sentence-transformers embeddings over hosted/LlamaIndex embeddings (recorded as DEC-003), specifically to limit how many third parties see scraped document content.
- **Remaining Issues:** Not run live against a real domain in this session (no `ANTHROPIC_API_KEY` configured here) — only offline/fixture-based tests and the authorisation-gate smoke tests have been run. Retrieval uses one fixed natural-language query per schema field rather than an adaptive strategy. `unstructured` (mentioned as a fallback parser in the original request) was not added, since pymupdf/python-docx/regex-based HTML stripping covered the required formats; add it later if a document format needs it. README.md still says "Documentation setup only" and was not updated, as that was outside this task's allowed changes.

## COLLECT-007 follow-up — Automatic .env loading

- **Task ID:** COLLECT-007 (follow-up)
- **Date:** 2026-09-26
- **Work Completed:** Added `crawler/env.py` (`load_env()`, idempotent, loads the repo-root `.env` via `python-dotenv`) and called it at the top of `main()` in `crawler/exposure/cli.py` and `crawler/brightdata.py`, so any key already in `.env` (Bright Data, Anthropic) is available without exporting it manually every session.
- **Files Changed:** Added crawler/env.py, crawler/tests/test_env.py. Updated crawler/exposure/cli.py, crawler/brightdata.py, crawler/requirements.txt (python-dotenv), docs/DECISIONS.md (DEC-005).
- **Verification:** `python -m unittest discover -s crawler/tests` ran 102 tests, all passing (offline, using a temp `.env` file, not the real one). Also ran a real smoke test: with `ANTHROPIC_API_KEY` unset from the shell but present in the repo's actual `.env`, `load_env()` in a fresh process populated `os.environ["ANTHROPIC_API_KEY"]` correctly.
- **Decisions:** CEO explicitly requested this; recorded as DEC-005. Noted in passing that `crawler/brightdata.py`'s docstring references a "DEC-004" that was never recorded in DECISIONS.md — pre-existing, left alone as out of scope.
- **Remaining Issues:** None. `crawler/infra.py` and `crawler/people_search.py` don't read any API key, so they weren't changed.

## COLLECT-007 follow-up — Live run against ahcsa.org.au; fetch-stage rate limiting

- **Task ID:** COLLECT-007 (follow-up)
- **Date:** 2026-09-26
- **Work Completed:** Ran the exposure-assessment tool live against ahcsa.org.au (CEO-named target, previously used for COLLECT-006 live testing). The first run fetched 39 candidate documents with no delay between requests and the site returned HTTP 429 on 30 of them — the discovery stage already rate-limited its own sitemap requests, but the document-fetch stage had no throttling at all, contradicting this task's own requirement and SECURITY.md's rate-limiting rule. Fixed by: throttling between document fetches (default 2s, `--rate-limit-seconds` on the CLI); adding a `RateLimitedError` (carries the site's `Retry-After` header when present) and retrying a 429'd fetch once after backing off. Re-ran live: 14 documents fetched, 0 errors.
- **Files Changed:** Updated crawler/exposure/fetch.py (RateLimitedError, 429 handling), crawler/exposure/cli.py (throttle + one retry, `--rate-limit-seconds`), crawler/tests/test_exposure_fetch.py, crawler/tests/test_exposure_cli.py (regression tests for throttling and retry-then-succeed).
- **Verification:** `python -m unittest discover -s crawler/tests` ran 106 tests, all passing (offline). Live re-run against ahcsa.org.au produced a real exposure report with 0 fetch errors: disclosed office address (220 Franklin Street, Adelaide), named vendors (Netsuite, Tauondi Aboriginal College, ASQA), and support contact patterns (email/phone), each with a verbatim quote and source URL — written to `output/live-exposure-ahcsa.json` and `.md` (git-ignored, not committed).
- **Decisions:** None beyond the approved task scope; this is a correctness fix found via live testing, matching the pattern of the COLLECT-006 live-run fixes.
- **Remaining Issues:** Retry is a single attempt with a fixed/`Retry-After` backoff, not a full exponential-backoff policy; sufficient for this site but a more aggressively rate-limited target could still see errors. `key_named_staff` was `not_stated` on this run — none of the 14 fetched documents happened to name an individual with a title (unlike the first run, which had fetched different documents from the set that hit 429s and included a couple of named-staff mentions), illustrating that which documents succeed affects which facts get extracted.

## COLLECT-007 follow-up — Timestamped default output files

- **Task ID:** COLLECT-007 (follow-up)
- **Date:** 2026-09-26
- **Work Completed:** CEO noted that re-running with the same `--json-output`/`--markdown-output` path overwrites the previous report (confirmed: that's exactly what happened between the two ahcsa.org.au test runs above). Added `default_output_paths()`: when `--json-output`/`--markdown-output` aren't given, the CLI now writes to `output/exposure-<domain-slug>-<UTC timestamp>.json`/`.md`, a new pair of files every run, instead of printing JSON to stdout and skipping the Markdown file (the prior default).
- **Files Changed:** Updated crawler/exposure/cli.py (`default_output_paths`, always-write-a-file default), crawler/tests/test_exposure_cli.py (tests for the slugging/timestamping and that consecutive runs get different paths).
- **Verification:** `python -m unittest discover -s crawler/tests` ran 108 tests, all passing. Live smoke test (`--max-documents 1`, to keep it cheap) against ahcsa.org.au confirmed real behaviour: produced `output/exposure-ahcsa-org-au-20260926T123539Z.json`/`.md` without touching the earlier `output/live-exposure-ahcsa.json`/`.md` from the manually-named runs.
- **Decisions:** CEO explicitly requested this (option 2 of two offered: auto-generated per-run filenames vs. the operator picking a new name each time).
- **Remaining Issues:** None. `output/` is already git-ignored, so accumulating report files there is not committed.

## COLLECT-007 follow-up — Deterministic domain/email extraction

- **Task ID:** COLLECT-007 (follow-up)
- **Date:** 2026-09-26
- **Work Completed:** CEO asked for the tool to look for "@domains" in scraped documents for the team's own use (confirmed: also any bare domain/URL mentioned, not just email domains; confirmed the existing SECURITY.md retain-but-don't-publish rule for contact data applies here too). Added `crawler/exposure/domains.py`: a deterministic (non-LLM) regex scan for email addresses, explicit URLs, and "www." mentions, run over every fetched document independently of the LLM extraction step (so a domain isn't missed just because it's outside the fixed retrieval queries). Wired into each normalizer in fetch.py: HTML scans visible text plus actual `<a href>` targets (mailto: included); PDF scans each page's text plus `page.get_links()` URI annotations (catches link targets with no visible text); DOCX scans paragraph text. Results attached to `NormalizedDocument.domain_mentions`, aggregated and deduped into `EntityRecord.domain_mentions` in cli.py, and shown in a new "Domains and email addresses found" report section (grouped by domain; own-domain mentions collapsed to a count in Markdown, full detail retained in JSON).
- **Files Changed:** Added crawler/exposure/domains.py, crawler/tests/test_exposure_domains.py. Updated crawler/exposure/fetch.py, crawler/exposure/schema.py (`EntityRecord.domain_mentions`), crawler/exposure/cli.py (aggregation), crawler/exposure/report.py (new report section, `other_domain_mentions()`), crawler/tests/test_exposure_fetch.py, test_exposure_report.py, test_exposure_cli.py, docs/SECURITY.md.
- **Verification:** `python -m unittest discover -s crawler/tests` ran 137 tests, all passing. Live-tested against ahcsa.org.au three times while fixing real issues the live runs exposed (see Decisions): final run found genuine third-party domains with correct provenance — a training-portal LMS vendor (app.axcelerate.com), the org's LinkedIn company page, live SEEK job postings, and an external contact email in a PDF (ats@australiantherapeutic.com) — with zero false positives, and the target's own 204 internal links summarised to a one-line count in the Markdown report instead of drowning the useful findings.
- **Decisions:** None beyond the CEO's explicit request; two real bugs were found and fixed via live testing rather than being scope changes: (1) scanning entire raw HTML matched a WordPress retina-image `srcset` attribute (`logo@2x-576x432.png`) as a false-positive email, and flooded the report with the site's own CSS/JS/feed/oembed URLs — fixed by scanning only visible text plus `<a href>` targets specifically (not `<link>`/`<script>` tags), plus filtering out common static-asset extensions; (2) that asset-extension filter initially missed URLs with a cache-busting query string after the extension (`style.css?ver=7.1.2`), because checking the last "." in the raw string found the query string's dot, not the extension's — fixed by checking the URL's parsed path specifically.
- **Remaining Issues:** DOCX hyperlinks stored as OOXML relationships (not part of `paragraph.text`) aren't extracted, only visible text — no DOCX files appeared in live testing so far, so this hasn't been verified against a real one. The regex approach will still miss unusual formats (e.g. an email split across HTML markup) that a real HTML parser might catch; acceptable for this tool's purpose given the deliberate choice not to add a full HTML-parsing dependency.
