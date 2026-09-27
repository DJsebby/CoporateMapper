# Discovery-to-database pipeline

The runner connects the existing components in this order:

```text
PublicWebsiteDiscoverer.discover(website)
    → Prioritiser.rank_urls(discovered URLs)
    → PublicURLFetcher.fetch_page(selected URL)
    → Extractor.process(PageDocument)
    → Neo4j Person and PersonEvidence records
    → people API and UI with enrichment
```

Discovery identifies candidate URLs. The prioritiser ranks them; it does not extract people. The crawler downloads and normalises selected pages, including their JSON-LD and original HTML. The extractor identifies explicit people and writes their fields, confidence, source URL, timestamp, and minimized permitted evidence using the existing storage contract. Raw source objects and biographies are not persisted by new runs.

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

The command prints a JSON report with discovered/valid/eligible/selected URL counts, a `discovery_failure_count`, successful fetches, pages containing people, person evidence records processed, distinct person identities, and each selected page's priority and outcome.

| Status | Meaning |
| --- | --- |
| stored | The extractor returned person records and its write transaction completed |
| no_people | The page was processed but contained no supported person records |
| fetch_failed | The crawler could not retrieve the page; the runner continues with later URLs |
| skipped_response | The response had a failed HTTP status or unsupported content type |
| extraction_or_storage_failed | Extraction/persistence raised an error; the run stops |

`records_stored` counts processed person evidence records, not newly created nodes. One person may have multiple evidence records. The existing MERGE logic deduplicates identical records, while a later crawl has a new observation timestamp and can add new evidence.

Exit codes are 0 for a completed run, 1 for setup or stage failures, 2 for invalid arguments or incomplete discovery/page fetches, and 130 for keyboard interruption. Known discovery failures are counted and reported; a missing robots file or default sitemap does not make an otherwise useful discovery fail by itself. An empty discovery result is printed with a diagnostic and never proves the site has no people. Database errors are never reported as successful writes. A failed run prints the partial report; earlier page transactions remain committed.

## Use in Python

```python
from database import connected_extractor
from pipeline import Pipeline

with connected_extractor() as extractor:
    with Pipeline(extractor) as pipeline:
        report = pipeline.run("https://example.com", max_pages=20)
        print(report.records_stored, report.unique_people)
```

Discovery, prioritisation, crawling, and extraction can all be injected for tests. The pipeline closes HTTP clients it creates; injected components and the Neo4j driver remain caller-owned. The default adapters share the enrichment public-source policy. The older standalone crawler helpers remain available for explicitly injected/manual checks.

## Existing component limits

- Person extraction supports Schema.org Person JSON-LD embedded in HTML, HTML microdata, and the staff-card layouts described below. The public default fetcher also supports standalone JSON/JSON-LD responses. Other HTML layouts, ordinary page text, social posts, and inferred interests need additional extraction rules. No NLP or model-based inference was added.
- Organisation membership requires an explicit person/card field or a matching organisation name and team-page heading as described below. A target website alone does not assign people to that organisation.
- Default discovery reads one entry HTML page, at most ten robots-advertised/default XML sitemaps, and retains at most 500 same-origin content candidates. It supports sitemap indexes, follows entry-page links, and avoids availability probes. `max_pages` limits subsequent selected content attempts; bounded metadata/robots requests are additional.
- Both discovery and content fetching use the public-only transport: DNS/IP pinning, private-network and redirect checks, robots enforcement, response/time limits and no authentication/CAPTCHA bypass. Advertised public CDN sitemap metadata is allowed; content candidates remain on the initial or redirected employer origin. Disallowed robots paths are not collected as candidates. Legacy manual helpers are not the default pipeline transport.
- The crawler does not execute page JavaScript. Failed or unsupported responses are reported without attempting alternate access methods.

## Staff cards and email links

The extractor also reads ordinary HTML staff cards without requiring Schema.org Person markup:

- `team-link` cards use the visible `t-flags` name and the first nonempty direct role paragraph, excluding telephone labels/links. This covers the Adelaide BMW team-page layout. Image alternative text is not used as a name.
- `team-member`, `staff-card`, `person-card`, `team-card`, and `staff-member` cards use a name element (`name`, `person-name`, `staff-name`, `team-name`, or `member-name`) or an h2–h4 heading. Role classes are `role`, `position`, `job-title`, `member-title`, and `team-position`.
- Name links and explicitly classed profile links can supply HTTP(S) profile URLs. Arbitrary links in a card are not person identifiers. Nested cards and microdata Person scopes keep their own fields.
- Organisation fields use `organisation`, `organization`, or `company` classes. Alternatively, a page heading must explicitly match a structured Organization/Corporation/LocalBusiness/AutoDealer name followed by `Team Members`, `Team`, or `Staff`; an organisation name elsewhere on the page is insufficient.

Email extraction follows `mailto:` links within each card, decodes percent-encoded recipients, and omits subject/CC/BCC values and empty or placeholder links such as `mailto:#`. Multiple valid recipients are preserved. It also reads the Joomla email-cloaking template used on the Adelaide BMW page: literal string concatenations are decoded only when they construct a mailto link for a matching cloak element in the same card. General JavaScript, dynamic calls, and unsupported statements are not executed or guessed. Telephone links within the card are retained separately from job titles. No email is sent or contact form submitted.

Persisted staff-card evidence has method `html-staff-card`, a source URL, fetch time, HTML line/column and permitted typed findings. Raw Joomla scripts and source objects are used transiently during parsing and omitted from new database writes. It does not claim that the page supplied Schema.org markup. Existing confidence weights are reused: name/card 0.60, explicit profile +0.15, role +0.10, organisation +0.10, contact +0.05. These measure completeness, not verified identity. UI scores remain `-`.

Repeated staff entries retain separate evidence and use the existing source-plus-name identity fallback unless an explicit profile exists. Missing email addresses remain empty; names are never used to invent email addresses. Sites with other card structures or contact scripts need additional adapters.

## Person images

The extractor retains image URLs explicitly associated with a person: Schema.org `Person.image` values and images inside supported staff cards. Relative references are resolved against the fetched page URL. The resulting `image_urls` are stored in the existing Neo4j person evidence JSON and returned by the people API, without changing person identity or completeness scores.

This records a source-provided portrait association; it does not detect faces or identify a person from an image. Images elsewhere on a page are not assigned to people. Image URL forms include strings, ImageObject fields/local references, microdata image properties, and staff-card image src/lazy-src/srcset/picture markup. CSS background images and JavaScript-rendered images are not collected. Malformed link/image URLs are skipped by the crawler so valid neighbouring people can still reach extraction. No image files are downloaded or stored, and older records need their source page crawled again to gain image URLs. The UI falls back to initials for missing or broken images.

## Verification

Run the new offline tests:

```bash
.venv/bin/python -m unittest -v test_pipeline test_staff_cards test_public_company_sources
```

Run named regression suites, including the opt-in live Neo4j checks:

```bash
RUN_NEO4J_TESTS=1 .venv/bin/python -m unittest -v test_pipeline test_extractor test_staff_cards test_api test_demo
```

Live pipeline tests still use simulated HTTP with real discovery/parsing/crawling/extraction, write only UUID-isolated fictional records, verify those records through the UI API, and clean them up. No third-party site is contacted.

The existing `tests/test_*.py` files are manual network checks. Importing them does not issue requests; invoking them directly still uses external services. Use the named modules above for offline regression verification.
