# Testing Requirements

The CEO requires test cases for implementation work from this point forward. These requirements define verification expectations, not approval for additional product features.

## Requirements for future work

- Add or update repeatable tests for new behaviour and bug fixes in the same task. Bug fixes must include a regression case for the reported failure.
- Assert observable outcomes against explicit expected values, not only that code runs without exceptions.
- Cover normal inputs, relevant edge cases, invalid inputs, and meaningful failure paths. For persistence changes, verify actual stored results and repeat-write behaviour against the supported database when available.
- Keep unit tests independent of network services. Make live integration tests explicitly opt-in, document prerequisites and commands, and report skipped tests separately from passed tests.
- Use fictional fixtures. Database tests must use unique identities, clean up only their own records even after assertion failures, and never delete unrelated data or print credentials.
- Record the test command, actual outcome, and verification limitations in COMPLETED.md. Do not claim tests prove all possible inputs or untested concurrency behaviour.

## Extractor acceptance cases

| Behaviour | Required evidence |
| --- | --- |
| JSON-LD extraction | Nested graphs, local references, URL reference objects, multiple names/roles, whitespace and contact normalisation |
| HTML microdata | Person and organisation scopes stay separate; nested people do not inherit each other's properties; itemref and void elements work |
| Confidence | Exact expected scores, stable ordering for ties, and no boost from duplicate appearances |
| Malformed records | Missing names, invalid values, and malformed URLs do not prevent valid neighbouring records from being extracted |
| Identity | Explicit identifiers/profile URLs give stable keys; namesakes on different pages and page-local blank nodes remain separate |
| Page eligibility | Failed HTTP responses, unsupported content types, and empty pages do not open a database session |
| Persistence contract | Parameterised statements, one write transaction per processed page, result consumption, session closure, and propagated database errors |
| Live Neo4j storage | Round-trip person/evidence data, no duplicate evidence on repeated writes, preserved conflicting claims, maximum confidence retained, and test data cleanup |

## Run the tests

From the repository root, offline tests require only Python's standard library:

```bash
python3 -m unittest -v test_extractor
```

Expected: 11 offline tests pass; one live test is skipped.

For the full suite, start the local database, install the existing dependency if necessary, and load your local credentials:

```bash
docker compose up -d
.venv/bin/python -m pip install -r requirements.txt
set -a
source .env
set +a
RUN_NEO4J_TESTS=1 PYTHONPATH=app:tests .venv/bin/python -m unittest -v test_extractor
```

Wait for Neo4j to finish starting before the live run (use docker compose logs --tail=30 neo4j to inspect startup). Expected: all 12 tests pass. Connection or authentication problems fail the enabled live test rather than silently skipping it. See [NEO4J.md](NEO4J.md) for initial setup. No extra test packages are required; requirements.txt continues to list Python dependencies only.

## People UI acceptance cases

- Person nodes and the equivalent list display names, positions, and a literal `-` score; extraction confidence never becomes the score.
- Organisation selection and case-insensitive grouping include unassigned people. Search applies before pagination so every matching person can be reached.
- Detail links open all stored profile fields and original evidence, preserve conflicting claims, support direct hash links, and close with Escape. Only HTTP/HTTPS values become external links.
- Verify empty, loading, missing-person, and database-error states, including retry. Database errors must not expose credentials.
- Verify a readable default mobile list, no horizontal page overflow, map pan/zoom controls, and keyboard-operable details.
- API tests use an injected store and verify read-only managed transactions, targeted detail queries, session cleanup, pagination validation, and driver ownership. Browser tests mock API responses; they do not replace live database verification.

Install the existing API test dependency and run offline Python tests:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
PYTHONPATH=app:tests .venv/bin/python -m unittest -v test_api test_extractor
```

Run the frontend build and browser tests:

```bash
npm ci --prefix frontend
cd frontend
npx playwright install chromium
npm run build
npm test
```

Playwright starts a temporary frontend server on port 5174. Tests use synthetic API fixtures and include a screenshot for visual review in ignored frontend/test-results/. Enable the existing RUN_NEO4J_TESTS flag for live extractor and extractor-to-API verification as described above. The combined Python suite contains 26 cases (24 offline and two opt-in live cases); the browser suite contains seven cases.

## Serper manual query

`test_name.py` sends one live query using the name, company, and role configured in the file, then prints Serper's raw response JSON. It requires `SERPER_API_KEY` in local `.env` or the process environment, network access, and consumes one Serper query credit. Run it only when you intend to make that request.

In PowerShell, run:

```powershell
python test_name.py
```

## Demo seed and cleanup acceptance cases

- Demo fixtures must be fictional, deterministic, and clearly labelled, with stable IDs/evidence timestamps so repeated runs do not add duplicates.
- The default CLI action seeds the demo; --delete invokes only cleanup. Each invocation uses a single managed write transaction.
- Cleanup must require exact fixture IDs and explicit ownership markers. It must preserve unrelated nodes/relationships, non-demo evidence attached to demo people, shared evidence, and edited evidence. Repeated cleanup must be safe.
- Seeding must refuse unowned ID collisions before making changes. Live tests must use unique test namespaces so they cannot delete the visible demo or user data.
- Run PYTHONPATH=app:tests .venv/bin/python -m unittest -v test_demo for four offline cases (four live cases skipped), or enable RUN_NEO4J_TESTS=1 for all eight. See [DEMO.md](DEMO.md) for usage.

## Discovery-to-database pipeline acceptance cases

- Exercise actual WebsiteDiscoverer, robots/sitemap parsers, Prioritiser, URLFetcher, and Extractor together with isolated HTTP fixtures; assert stored person fields, organisation, confidence, and provenance rather than only call counts.
- Rank once, crawl in priority order, apply inclusive score bounds and a page-attempt limit, deduplicate fragment variants, and ignore invalid/non-HTTP candidates.
- Empty discovery, no eligible URLs, failed fetches, unsupported responses, and pages without supported person markup or staff cards must not produce person writes. Empty discovery is inconclusive when upstream errors are suppressed.
- Storage failures stop the run and expose partial outcomes without claiming an incomplete page was committed. Earlier page commits must remain explicit. URL priority and extraction confidence must never become the UI score.
- Close owned HTTP resources on completion/failure and leave injected clients and Neo4j drivers caller-owned.
- Provide an opt-in live Neo4j test with synthetic HTTP fixtures and UUID-isolated records, verify records are available through the people API, and remove only test data.
- Run named modules (test_pipeline, test_extractor, test_staff_cards, test_api, test_demo). Existing tests/test_*.py files are main-guarded manual network checks, not offline regression suites; importing them does not issue requests. See [PIPELINE.md](PIPELINE.md) for commands and component limitations.

## HTML staff cards and click-to-email acceptance cases

- Use fictional cards matching the reported Adelaide BMW layout and other explicitly supported staff-card classes. Assert names, roles, explicit organisations/profiles, exact completeness scores, source locations, and the `html-staff-card` method; never label inferred HTML records as Schema.org markup.
- Keep fields within the owning card. Exclude footer contacts, nested staff cards, nested microdata people, image-alt names, phone numbers in job titles, and arbitrary links as profile identities. Existing microdata people must not be duplicated by the staff-card adapter.
- Normalise mailto recipients, percent encoding, multiple recipients, and duplicate addresses. Ignore empty links, `mailto:#`, malformed addresses, and subject/CC/BCC parameters; never invent missing email addresses.
- Decode Joomla literal concatenations only when their constructed mailto link targets a matching cloak element in the same card. Cover entity semicolons, escaped quotes, multiline rendering, comments, unsupported reassignment/control flow, malformed escapes, and valid neighbouring cards. Never execute page JavaScript.
- Require explicit card organisation fields or an exact match between structured organisation name and a team-page heading. A domain, unrelated organisation record, or generic 'Meet the team' heading alone must not establish membership.
- Preserve stable source/name identities and separate evidence for repeated/conflicting entries. Verify parameterised repeat writes, pipeline handling of actual HTML through the crawler, and an opt-in live Neo4j/API round trip using isolated fictional records and scoped cleanup.
- Run `PYTHONPATH=app:tests .venv/bin/python -m unittest -v test_staff_cards` offline, or export the existing Neo4j settings and set `RUN_NEO4J_TESTS=1` for the live case. The original `test_extractor` module still needs only the standard library for offline tests. See [PIPELINE.md](PIPELINE.md) for supported layouts and limits.

## Graceful failures, person images, and activity preview

- Executable utilities must report failures concisely, avoid exposing credentials in exception text, return nonzero exit codes, and handle keyboard interruption. Importing manual runners must not contact external services.
- Verify missing configuration/dependencies, network failures, malformed responses, and cleanup using offline doubles. Keep library exceptions observable so failures are not mistaken for successful empty results.
- Extract only image URLs associated with supported person markup or the owning staff card. Cover relative URLs, ImageObject references, lazy images, malformed values, nested people/cards, and rejected non-HTTP or credential-bearing URLs.
- Image fields must not alter person identity, extraction confidence, or no-image evidence. Verify the stored JSON through an opt-in live Neo4j round trip with unique fictional records and scoped cleanup.
- API summaries and details expose deduplicated image URLs, newest evidence first. Existing records default to an empty list; corrupt image fields do not hide valid people.
- Browser checks cover portraits, broken/unsafe-image fallback, network error recovery, responsive layout, and a clearly labelled static Recent activity preview visible in empty/error states. Activity must not imply a live Neo4j connection yet.

Run the new offline suites alongside existing regression tests:

```bash
PYTHONPATH=app:tests .venv/bin/python -m unittest -v test_cli test_images test_pipeline test_extractor test_staff_cards test_api test_demo
npm run build --prefix frontend
npm test --prefix frontend
```

Enable `RUN_NEO4J_TESTS=1` with exported local Neo4j settings to run the isolated database checks.

## Australian enrichment and shared-demo acceptance cases

- Real and demo providers run through the identical worker and structured evidence policy; the demo flag accepts only authored built-in fixtures. Real routes reject fictional/model overrides and make zero Gemini requests even with a configured key.
- Verify quoted Australian searches, one attempt per employee/run, durable debit before requests, seven-day caches, explicit reruns, quotas, 15-page limits, private/redirect/robots controls, cancellation and interrupted-job recovery.
- Verify employee-specific Australian workplace proof, original employer-link identity anchors, namesakes/external review isolation, source-backed facts, conflicting observations, personal/sensitive/raw-data exclusion and identity-scoped dismissals.
- Keep Gemini's optional live fixture evaluation separate from offline mock tests. Never pass actual employee data to the model.
- `test_enrichment`, `test_enrichment_review`, `test_enrichment_policy`, `test_enrichment_sources`, `test_public_company_sources`, and `test_gemini_fixture_eval` cover these paths; `test_enrichment` has an opt-in isolated Neo4j test. Frontend browser tests cover selection, review, workplace evidence, progress, cancellation, source links and dismissals. See [ENRICHMENT.md](ENRICHMENT.md).


## Per-person population and fictional profile context

- An explicit per-person click creates one idempotent enrichment request; polling/reopening never searches. The table updates from saved findings, shows missing values and retains provenance and pending review decisions.
- Built-in fictional profiles vary in completeness. Synthetic sensitive examples stay outside the real evidence validator and collector; arbitrary identities, request bodies and modified stored fixture values must not enter Gemini.
- Save fictional table data before the outbound model request and persist attempts before sending. Restart/cancellation never silently replays requests, and late cancelled responses are discarded.
- Missing keys, provider quotas, malformed/unsupported context and transport failures leave the table available. Retry is explicit. Both context text and citations must match supported fixture options; missing fields must correspond to the populated subset.
- Verify profile → job → Neo4j → context → API and browser flows with isolated fictional fixtures, including full and partial inputs. Real workflow tests keep a configured Gemini key and assert zero model calls.
- Run `test_demo_profile_context` and `test_demo_profile_workflow` alongside the existing enrichment/Gemini regression suites; enable `RUN_NEO4J_TESTS=1` for isolated persistence checks. Browser tests cover real population, demo completeness, context progress/citations/failure/retry and responsive tables.
