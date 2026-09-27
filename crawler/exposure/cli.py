"""
End-to-end CLI for COLLECT-007.

Usage:
    python -m crawler.exposure.cli example.com --authorized-domain example.com --confirm

Each run writes a new, timestamped JSON and Markdown report under output/
(e.g. output/exposure-example-com-20260926T123045Z.json) rather than
overwriting a fixed file, unless --json-output/--markdown-output is given.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crawler.env import load_env
from crawler.exposure.authorization import AuthorizationError, require_authorization
from crawler.exposure.discovery import DEFAULT_MAX_CANDIDATES, DocumentDiscovery
from crawler.exposure.domains import DomainMention, dedupe
from crawler.exposure.extract import InstructorAnthropicClient, gather_passages
from crawler.exposure.fetch import DocumentFetcher, FetchError, RateLimitedError
from crawler.exposure.index import PassageIndex, chunk_document
from crawler.exposure.report import build_exposure_report, to_markdown
from crawler.exposure.schema import EntityRecord

log = logging.getLogger(__name__)

DEFAULT_FETCH_RATE_LIMIT_SECONDS = 2.0
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 5.0


def run(
    domain: str,
    *,
    max_documents: int = DEFAULT_MAX_CANDIDATES,
    rate_limit_seconds: float = DEFAULT_FETCH_RATE_LIMIT_SECONDS,
    discovery: DocumentDiscovery | None = None,
    fetcher: DocumentFetcher | None = None,
    index: PassageIndex | None = None,
    extraction_client=None,
    sleep: Any = time.sleep,
):
    discovery = discovery or DocumentDiscovery()
    fetcher = fetcher or DocumentFetcher()
    index = index or PassageIndex()
    extraction_client = extraction_client or InstructorAnthropicClient()

    errors: list[str] = []
    candidate_urls = discovery.discover(domain, max_candidates=max_documents)

    passages = []
    considered: list[str] = []
    domain_mentions: list[DomainMention] = []
    for position, url in enumerate(candidate_urls):
        if position > 0 and rate_limit_seconds > 0:
            sleep(rate_limit_seconds)
        try:
            document = _fetch_with_one_retry(fetcher, url, sleep)
        except FetchError as exc:
            errors.append(str(exc))
            continue
        considered.append(url)
        passages.extend(chunk_document(document))
        domain_mentions.extend(document.domain_mentions)

    index.build(passages)
    retrieved = gather_passages(index)
    facts = extraction_client.extract(retrieved)

    entity = EntityRecord(
        domain=domain,
        documents_considered=considered,
        facts=facts,
        domain_mentions=dedupe(domain_mentions),
        errors=errors,
    )
    return build_exposure_report(entity)


def _fetch_with_one_retry(fetcher: DocumentFetcher, url: str, sleep: Any):
    try:
        return fetcher.fetch(url)
    except RateLimitedError as exc:
        sleep(exc.retry_after or DEFAULT_RATE_LIMIT_BACKOFF_SECONDS)
        return fetcher.fetch(url)


def default_output_paths(domain: str, *, when: datetime | None = None) -> tuple[Path, Path]:
    """
    One pair of paths per run, so repeated runs against the same domain
    don't overwrite each other's report.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-") or "domain"
    timestamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    base = Path("output") / f"exposure-{slug}-{timestamp}"
    return base.with_suffix(".json"), base.with_suffix(".md")


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(
        description="Assess public-document exposure for a single authorised domain."
    )
    parser.add_argument("domain", help="Target domain, e.g. example.com")
    parser.add_argument(
        "--authorized-domain",
        required=True,
        help="The exact domain you are authorised to assess (must match the target domain).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirms you have authorisation to assess --authorized-domain.",
    )
    parser.add_argument("--max-documents", type=int, default=DEFAULT_MAX_CANDIDATES)
    parser.add_argument(
        "--rate-limit-seconds",
        type=float,
        default=DEFAULT_FETCH_RATE_LIMIT_SECONDS,
        help="Seconds to wait between document fetches (0 disables throttling).",
    )
    parser.add_argument(
        "--json-output",
        help="Write the JSON report to this file. Default: a new output/exposure-<domain>-<timestamp>.json each run.",
    )
    parser.add_argument(
        "--markdown-output",
        help="Write the Markdown report to this file. Default: a new output/exposure-<domain>-<timestamp>.md each run.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        require_authorization(
            args.domain, authorized_domain=args.authorized_domain, confirmed=args.confirm
        )
    except AuthorizationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report = run(args.domain, max_documents=args.max_documents, rate_limit_seconds=args.rate_limit_seconds)

    default_json, default_markdown = default_output_paths(args.domain)
    json_path = Path(args.json_output) if args.json_output else default_json
    markdown_path = Path(args.markdown_output) if args.markdown_output else default_markdown

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(to_markdown(report), encoding="utf-8")

    log.info(
        "%d documents considered, %d findings, %d errors -> %s, %s",
        len(report.entity.documents_considered), len(report.findings), len(report.entity.errors),
        json_path, markdown_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
