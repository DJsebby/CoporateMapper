# Australian employee enrichment

The real and fictional runs use the same `EnrichmentEngine`, structured parser, validation, identity checks, review decisions, Neo4j evidence writes, job progress, cancellation and budget accounting. Only the source provider changes: `LiveSources` uses Serper/public pages; `DemoSources` returns authored copies of the existing 23 `demo.py` people and fixture responses. It does not label arbitrary records as fictional.

## Populate a profile and demonstrate AI context

Open a person's details and click **Populate additional information** for real employees. This creates a one-person enrichment job using the same Australian eligibility, identity review, seven-day search cache and limited Serper allowance as bulk enrichment. The table refreshes as saved findings change; email means an explicitly published business contact, and sports appear only as supported general interests. Missing values remain **Not recorded**. Opening a profile, polling activity or refreshing the browser never starts a search. Pending identity/workplace reviews remain in Recent activity.

Built-in demo people have a separate **Populate demo information** action. It saves an authored fictional table to Neo4j before making one Gemini request. The resulting **Profile summary**, **Information gaps**, and **Privacy implications** appear in the same profile with references to table facts. Alex Morgan has a full fixture, Jordan Lee a partial fixture, and Sam Taylor a minimal fixture; the other demo people also vary in coverage. Demo addresses, personal emails, religion and sexual orientation are authored fictional values, with reserved `.invalid` sources. These extra fields are never collected for real people and do not enter the real evidence policy.

Only exact built-in identities can use these routes. The server reconstructs the approved fictional catalog and checks each saved table value and its metadata before sending it to Gemini. It never sends ordinary employee rows, user-supplied profile content or raw source JSON. Gemini selects and orders supported factual statements and general privacy implications from constrained options; the app validates both the prose and citations. A gap means the field is absent from the current table, not that it cannot be found elsewhere.

The populated table, model result and progress persist in the existing Neo4j job records. Missing credentials, quota limits, malformed output and timeouts preserve the table and show an error. Use the explicit context retry action for another request; reopening or refreshing does not retry. Cancellation discards late model output. A server restart marks in-flight work interrupted and never repeats the request automatically. Demo context uses the same single background worker, with no Serper requests.

To start this demonstration, keep the Gemini key/model in the server's `.env`, seed the existing fictional people if needed with `.venv/bin/python demo.py`, build the UI and start the local API using the commands below. `enrich.py --demo` still tests the shared rules-based collection path; the per-profile button additionally tests the fictional sensitive table and Gemini context.

## Test the shared collection workflow with your demo

From the repository root, stop any running API with Ctrl+C, then run:

```bash
docker compose up -d
.venv/bin/python enrich.py --demo
npm run build --prefix frontend
set -a
source .env
set +a
.venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Keep the last command running: tests and demo commands finish and do not leave a web server listening. `enrich.py` loads `.env` itself. On Windows, use your virtual environment's `python` command and load the same environment settings before starting Uvicorn.

The flag seeds the existing demo if needed and fetches fictional employer profiles with explicit Australian workplace evidence, business contacts, portraits, skills, credentials, and general interests. No Serper or Gemini key is needed and no external requests are made by the demo provider. The activity box shows the persisted job; Alex has a fictional external profile to review, and the unassigned person lacks employer evidence and remains for review without spending a search. An unresolved demo match is an intentional test case, not a successful identity association.

Open person details to inspect each fact's value, original source, observed date and extraction method. Demo source/portrait URLs use reserved `.invalid` domains, so their external links cannot load; portrait initials are expected. Accept or reject candidates in the activity box, dismiss an incorrect finding, and refresh to confirm persistence. Demo review continuations continue using fixture sources.

A second run reuses eligible cached searches and deduplicates facts. First finish or cancel the previous job's pending reviews, then stop the API before running the CLI again. To exercise a deliberate new search against the same fictional responses:

```bash
.venv/bin/python enrich.py --demo --search-again
```

Demo accounting/cache are separate from real credits. Production UI creation rejects the built-in demo identities and directs you to this command. The OS worker lock prevents the CLI and API from running workers simultaneously. `demo.py --delete` keeps its original conservative cleanup: it retains people with added enrichment evidence rather than deleting those later records.

## Run real collection

Discover people from an employer website with the [company pipeline](PIPELINE.md), whose default discovery and fetch adapters use the same public-source access policy, then use the UI's **Select employees for enrichment** control (up to 20 per job). Configure server-side settings in `.env` first:

```dotenv
SERPER_API_KEY=your_actual_key
ENRICHMENT_SEARCH_ALLOWANCE=5
GEMINI_MODEL=gemini-3.8-flash
GEMINI_API_KEY=replace_with_your_gemini_api_key
```

The real allowance defaults to **zero**. Set a small total allowance no greater than the provider credits you have available. The ledger counts attempts cumulatively across jobs and restarts. Increasing the setting deliberately increases this workspace's total ceiling; restarting does not reset usage. Provider 402/429/quota errors stop further searches. There is no paid fallback or automatic quota reset. This version does not infer the provider's remaining balance from Serper's `credits` response field. A provider-exhausted workspace remains stopped; clearing that durable state is an explicit operator maintenance action after verifying the provider allowance.

**Enrich selected** may use a seven-day result cache. **Search again** shows the additional allowance and bypasses that cache. Refresh, profile opening, job polling and ordinary retries of the same job-creation request do not search. Each employee gets at most one quoted query per run: `"Full Name" "Company Name" Australia`, `gl: "au"`, `num: 10`; no `intext:`, expansion, pagination or automatic search retries. Attempts are persisted before the outbound request, so a timeout consumes the reservation. Database managed-transaction retries never repeat external requests.

Each employee gets at most 15 content-page attempts, including employer-linked profiles, failed fetches and supplied workplace-review pages. Robots requests and bounded redirect checks are additional transport requests. If all page attempts have been used, no new search is sent because its results could not be checked. Public transport pins validated public IP addresses, rejects private/mixed DNS results and private redirects, checks robots/access restrictions, and caps redirects, response size and elapsed time. It never signs in or bypasses CAPTCHA. Global domains, including `.com`, are eligible.

Australian eligibility requires explicit employee `workLocation`/`jobLocation` evidence with Australia, including an assigned office's city/country. A company's headquarters, `.au` domain and Serper locale do not prove an employee works in Australia. Uncertain employees enter review before a search. A supplied workplace source is fetched through the same worker/page budget and must contain consistent identity and explicit workplace evidence; an operator checkbox alone is insufficient.

Consistent, person-specific links from original employer evidence can be associated automatically. External search matches remain pending until the operator confirms identity. A name alone never merges people. Accepted external links do not become employer-trusted links on later runs. Previously established employee workplace evidence can support review of an external publication/profile that does not repeat location.

## Evidence and privacy boundaries

Collection supports explicitly structured roles, skills, qualifications, dated professional history, explicitly authored publications, profile links and portrait URLs. Contacts require explicit business publication (a business/work contact point or employer staff card without a personal/private label). Office location is city/country only. Interests use a small supported vocabulary/rule set and retain tense, without club, venue, schedule or precise location.

Religion, sexual orientation, health details, political beliefs, home addresses, personal contacts, family relationships and routines are excluded. Real biographies are not sent to a model or broadly parsed. Search snippets are not evidence. Unsupported findings or findings without original page URL/date are omitted. Source objects and HTML remain transient; new persisted evidence is minimized, and legacy API evidence is filtered. Historical raw database records are not deleted by this change.

Facts have category/value, source URL/name, observation date, minimal permitted evidence and extraction method. Stable IDs deduplicate repeated observations of the same value on the same page. Different values and sources remain distinct. Dismissals apply to a fact for a particular employee; another independently sourced observation of the same value remains visible until separately dismissed.

## Gemini fixture evaluation

The common real/demo collection engine is rules-based and makes **zero Gemini requests**, even with a configured key. The additional demo profile workflow above can call Gemini using only validated built-in fictional table data. The standalone evaluation command below remains available and regenerates its inputs from an authored fixture. No arbitrary fictional override, fixture path or employee record can enable real-employee model processing.

Offline mocked evaluation:

```bash
.venv/bin/python gemini_fixture_eval.py --demo
```

After adding your server-side key, one live fictional-fixture request:

```bash
.venv/bin/python gemini_fixture_eval.py --demo --live
```

The default model is `gemini-3.8-flash`; the client uses the Interactions API with `store: false`, low thinking, and a 4,096-token output cap. It requests structured JSON and validates every returned value and source against the same supported fixture facts. Missing credentials, malformed/unsupported responses, incomplete output and quota errors fail clearly without retries. Offline success verifies the adapter and application rules, not live Google availability or quota. See Google's [pricing](https://ai.google.dev/gemini-api/docs/pricing), [structured-output documentation](https://ai.google.dev/gemini-api/docs/structured-output) and [terms](https://ai.google.dev/gemini-api/terms). Real employee information remains out of the unpaid model service.

If an older setup reports HTTP 404 with `gemini-2.5-flash`, Google has restricted that model to previous active users. Update `GEMINI_MODEL=gemini-3.8-flash` in the project-root `.env`; keep your existing `GEMINI_API_KEY` there. An exported shell value takes precedence over `.env`, so clear an old model override before retrying:

```bash
unset GEMINI_MODEL
.venv/bin/python gemini_fixture_eval.py --demo --live
```

The command loads `.env` each time; restarting the web server is unnecessary. The standalone live request requires neither Neo4j nor Serper. It evaluates one built-in fictional profile without populating the UI database. Use the profile button above to test the complete fictional table → Gemini → saved UI context workflow.

## API and persistence

| Endpoint | Behaviour |
| --- | --- |
| `POST /api/enrichment/jobs` | `{person_ids, idempotency_key, search_again?}`; creates one job; unknown fields rejected |
| `GET /api/enrichment/jobs` | Recent 100 jobs and real search allowance; no search |
| `GET /api/enrichment/jobs/{id}` | Job, per-employee stage, counts and candidates |
| `POST /api/enrichment/jobs/{id}/cancel` | Cooperative cancellation; retains committed findings |
| `POST /api/enrichment/jobs/{id}/items/{item_id}/review` | `{candidate_id, decision, australian_work_source?}`; accept/reject or queue workplace verification |
| `POST /api/demo/profiles/{id}/populate` | `{idempotency_key}`; built-in fictional table, followed by one model context request |
| `POST /api/demo/profiles/{id}/context` | `{idempotency_key}`; explicit context retry on already populated canonical fictional findings |
| `GET /api/people/{id}` | Sourced real findings; built-in fixtures additionally expose validated `demo_profile` table/context |
| `POST /api/people/{id}/findings/{finding_id}/dismiss` | Dismiss one employee's sourced observation |

`Person` / `PersonEvidence` / `HAS_EVIDENCE` remain the fact storage path. New `EnrichmentJob`, `EnrichmentAllowance`, `EnrichmentSearchCache` and `DismissedFinding` records hold persistent control state. Jobs store minimized JSON progress. One API process has one background worker; no Celery/Redis service or database migration is required. There are no concurrent-process guarantees beyond the local OS lock; do not run multiple workers or use a shared deployment.

On restart, queued/running jobs become interrupted; pending reviews and committed facts survive. No interrupted search is silently resumed. Cancellation is checked between requests and before commits; the current bounded request may finish first. A new explicit run can reuse a valid cache or consume its displayed allowance. There is no scheduled monitoring, risk score, training advice or employee account system.

## Verification

Use fictional isolated fixtures only:

```bash
.venv/bin/python -m unittest -v test_enrichment test_enrichment_review test_enrichment_policy test_enrichment_sources test_gemini_fixture_eval test_demo_profile_context test_demo_profile_workflow test_public_company_sources
# After exporting .env, with local Neo4j running:
RUN_NEO4J_TESTS=1 .venv/bin/python -m unittest -v test_enrichment test_demo_profile_workflow
npm run build --prefix frontend
CI=1 npm test --prefix frontend
```

Live Neo4j tests use unique fixture namespaces and clean up only their own records. Browser tests mock API responses. Live Serper requests are intentionally absent; live Gemini verification requires the explicit fixture command after you add a key.
