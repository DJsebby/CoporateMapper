# Demo data

The demo creates 17 fictional people using the real extractor's parsing and confidence logic, then stores their person/evidence records with explicit demo ownership markers. It makes no network requests to the fictional sources.

## Load the demo

From the repository root, with Neo4j running:

```bash
set -a
source .env
set +a
.venv/bin/python demo.py
```

Refresh the People map at <http://localhost:8000> (see [UI.md](UI.md) to start it). You will see:

- **Meridian Labs (Demo):** 12 people, enough to exercise pagination.
- **Northstar Advisory (Demo):** five people, including one advisor shared with Meridian.
- **Unassigned:** one person with no recorded organisation.
- One person without a position, plus fictional contacts, profiles, and source evidence for inspecting details.

There are 17 distinct people, despite the shared advisor appearing in both organisation counts. UI scores remain `-`.

The demo uses stable IDs, source URLs, and timestamps. Run the command again to restore missing demo data without adding duplicate records. Run seed and cleanup commands sequentially, not concurrently; database uniqueness constraints remain outside this task.

## Delete only this demo

```bash
.venv/bin/python demo.py --delete
```

Load `.env` first if this is a new terminal. Refresh the UI after deleting.

Cleanup requires both the exact demo IDs and their `demo_dataset` ownership marker. It deletes only owned demo relationships and unchanged demo evidence; it deletes a person node only when no relationships remain. It never uses a broad database deletion or removes unrelated links. Existing unmarked records are never claimed: seeding aborts atomically if an expected ID already exists without the matching demo marker.

If you attach other evidence or relationships to a demo person, that person is retained. Shared evidence and edited evidence are also retained and reported. Repeating cleanup is safe. Keep the version-one fixture IDs and timestamps stable: a future dataset revision needs its own namespace and cleanup support for existing versions.

## Test the demo safely

```bash
.venv/bin/python -m unittest -v test_demo
# With .env exported and Neo4j running:
RUN_NEO4J_TESTS=1 .venv/bin/python -m unittest -v test_demo
```

Four offline cases check deterministic fictional fixtures, isolated namespaces, and CLI flags. Four opt-in live cases verify repeated seeds, full/scoped cleanup, unrelated records, extra evidence, shared evidence, edited records, and ownership collisions. Tests use unique namespaces and clean up only their own records; the default demo remains available in the UI.

## Exercise the shared enrichment pipeline

With the API stopped, run `.venv/bin/python enrich.py --demo`. This uses the same engine, validation, review, job progress and Neo4j writes as real collection, with offline responses from authored copies of these same 17 fixtures. The original fixture IDs/cleanup fingerprints remain unchanged. See [ENRICHMENT.md](ENRICHMENT.md) for startup, expected pending reviews and optional fictional-only Gemini evaluation. Enrichment adds separately sourced evidence, so the original `demo.py --delete` conservatively retains enriched people with those additional links.
