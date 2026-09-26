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
RUN_NEO4J_TESTS=1 .venv/bin/python -m unittest -v test_extractor
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
.venv/bin/python -m unittest -v test_api test_extractor
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

## Demo seed and cleanup acceptance cases

- Demo fixtures must be fictional, deterministic, and clearly labelled, with stable IDs/evidence timestamps so repeated runs do not add duplicates.
- The default CLI action seeds the demo; --delete invokes only cleanup. Each invocation uses a single managed write transaction.
- Cleanup must require exact fixture IDs and explicit ownership markers. It must preserve unrelated nodes/relationships, non-demo evidence attached to demo people, shared evidence, and edited evidence. Repeated cleanup must be safe.
- Seeding must refuse unowned ID collisions before making changes. Live tests must use unique test namespaces so they cannot delete the visible demo or user data.
- Run .venv/bin/python -m unittest -v test_demo for four offline cases (four live cases skipped), or enable RUN_NEO4J_TESTS=1 for all eight. See [DEMO.md](DEMO.md) for usage.
