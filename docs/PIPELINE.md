# Discovery-to-database pipeline

The runner connects the existing components in this order:

```text
WebsiteDiscoverer.discover(website)
    → Prioritiser.rank_urls(discovered URLs)
    → URLFetcher.fetch_page(selected URL)
    → Extractor.process(PageDocument)
    → Neo4j Person and PersonEvidence records
    → existing read-only people API and UI
```

Discovery identifies candidate URLs. The prioritiser ranks them; it does not extract people. The crawler downloads and normalises selected pages, including their JSON-LD and original HTML. The extractor identifies explicit people and writes their fields, confidence, source URL, timestamp, and original evidence using the existing storage contract.

## Run it

From the repository root, with Neo4j running:

```bash
.venv/bin/python -m pip install -r requirements.txt
set -a
source .env
set +a
.venv/bin/python pipeline.py https://example.com --max-pages 20
```

Replace example.com with the website you intend to process. The integrated CLI verifies Neo4j connectivity before starting discovery. Refresh the [people UI](UI.md) after a run to see stored records. Discovery still starts from the website URL you supply.

Options:

- `--min-score`: minimum URL priority, default 40.
- `--max-score`: maximum URL priority, default 100.
- `--max-pages`: maximum content-fetch attempts after ranking, default 50.

Score bounds are inclusive. These defaults match the existing crawler's score-range method. URL priority is separate from extraction confidence; UI person scores remain `-`.

The runner normalises bare website hosts to HTTPS, removes URL fragments, deduplicates candidates, and ignores invalid/non-HTTP URLs and URLs with embedded credentials. It calls the prioritiser once and fetches the selected URLs in ranked order. It does not recursively crawl links from fetched pages.

## Read the results

The command prints a JSON report with discovered/valid/eligible/selected URL counts, successful fetches, pages containing people, person evidence records processed, distinct person identities, and each selected page's priority and outcome.

| Status | Meaning |
| --- | --- |
| stored | The extractor returned person records and its write transaction completed |
| no_people | The page was processed but contained no supported person records |
| fetch_failed | The crawler could not retrieve the page; the runner continues with later URLs |
| skipped_response | The response had a failed HTTP status or unsupported content type |
| extraction_or_storage_failed | Extraction/persistence raised an error; the run stops |

`records_stored` counts processed person evidence records, not newly created nodes. One person may have multiple evidence records. The existing MERGE logic deduplicates identical records, while a later crawl has a new observation timestamp and can add new evidence.

Exit codes are 0 for a completed run, 1 for setup or stage failures, and 2 for invalid arguments or a run containing failed page fetches. An empty discovery result is printed with a diagnostic: the discoverer currently suppresses some network/sitemap errors, so zero URLs does not prove the site has no people. Database errors are never reported as successful writes. A failed run prints the partial report; earlier page transactions remain committed.

## Use in Python

```python
from database import connected_extractor
from pipeline import Pipeline

with connected_extractor() as extractor:
    with Pipeline(extractor) as pipeline:
        report = pipeline.run("https://example.com", max_pages=20)
        print(report.records_stored, report.unique_people)
```

Discovery, prioritisation, crawling, and extraction can all be injected for tests. The pipeline closes HTTP clients it creates; injected components and the Neo4j driver remain caller-owned. WebsiteDiscoverer and URLFetcher also support context managers directly.

## Existing component limits

- Person extraction supports Schema.org Person JSON-LD embedded in HTML, HTML microdata, and the staff-card layouts described below. The existing crawler does not populate structured data from standalone JSON response bodies. Other HTML layouts, ordinary page text, social posts, and inferred interests need additional extraction rules. No NLP or model-based inference was added.
- Organisation membership requires an explicit person/card field or a matching organisation name and team-page heading as described below. A target website alone does not assign people to that organisation.
- The discoverer uses robots/sitemap discovery and probes candidate URLs before prioritisation. `max_pages` therefore limits crawler page attempts, not discovery requests or sitemap traversal.
- The existing robots parser collects both Allow and Disallow paths as candidates. It is not a robots-policy enforcement layer; this integration preserves that behaviour. Discovery can also return URLs outside the initial host. Configure/review target scope and collection rules before an external run; those policies were not redesigned in this task.
- The crawler does not execute page JavaScript. Failed or unsupported responses are reported without attempting alternate access methods.

## Staff cards and email links

The extractor also reads ordinary HTML staff cards without requiring Schema.org Person markup:

- `team-link` cards use the visible `t-flags` name and the first nonempty direct role paragraph, excluding telephone labels/links. This covers the Adelaide BMW team-page layout. Image alternative text is not used as a name.
- `team-member`, `staff-card`, `person-card`, `team-card`, and `staff-member` cards use a name element (`name`, `person-name`, `staff-name`, `team-name`, or `member-name`) or an h2–h4 heading. Role classes are `role`, `position`, `job-title`, `member-title`, and `team-position`.
- Name links and explicitly classed profile links can supply HTTP(S) profile URLs. Arbitrary links in a card are not person identifiers. Nested cards and microdata Person scopes keep their own fields.
- Organisation fields use `organisation`, `organization`, or `company` classes. Alternatively, a page heading must explicitly match a structured Organization/Corporation/LocalBusiness/AutoDealer name followed by `Team Members`, `Team`, or `Staff`; an organisation name elsewhere on the page is insufficient.

Email extraction follows `mailto:` links within each card, decodes percent-encoded recipients, and omits subject/CC/BCC values and empty or placeholder links such as `mailto:#`. Multiple valid recipients are preserved. It also reads the Joomla email-cloaking template used on the Adelaide BMW page: literal string concatenations are decoded only when they construct a mailto link for a matching cloak element in the same card. General JavaScript, dynamic calls, and unsupported statements are not executed or guessed. Telephone links within the card are retained separately from job titles. No email is sent or contact form submitted.

Staff-card evidence has method `html-staff-card`, a source URL, fetch time, HTML line/column, extracted fields, and the relevant contact source (including the original Joomla script when decoded). It does not claim that the page supplied Schema.org markup. Existing confidence weights are reused: name/card 0.60, explicit profile +0.15, role +0.10, organisation +0.10, contact +0.05. These measure completeness, not verified identity. UI scores remain `-`.

Repeated staff entries retain separate evidence and use the existing source-plus-name identity fallback unless an explicit profile exists. Missing email addresses remain empty; names are never used to invent email addresses. Sites with other card structures or contact scripts need additional adapters.

## Verification

Run the new offline tests:

```bash
.venv/bin/python -m unittest -v test_pipeline test_staff_cards
```

Run named regression suites, including the opt-in live Neo4j checks:

```bash
RUN_NEO4J_TESTS=1 .venv/bin/python -m unittest -v test_pipeline test_extractor test_staff_cards test_api test_demo
```

Live pipeline tests still use simulated HTTP with real discovery/parsing/crawling/extraction, write only UUID-isolated fictional records, verify those records through the UI API, and clean them up. No third-party site is contacted.

The existing `tests/test_*.py` files are manual scripts that issue live requests at import time. Do not use broad test discovery over that directory for offline verification; use the named modules above.
