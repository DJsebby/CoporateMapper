# Data Sources

Approved public information sources, their intended use, and applicable collection constraints.

No sources are currently in use. Google Custom Search (DEC-002) was withdrawn on 2026-09-26.

## Certificate transparency, public DNS, and RDAP (COLLECT-006)

- **Used by:** `crawler/infra.py`.
- **Purpose:** Map a target organisation's public domains and infrastructure: subdomains, DNS records, hosting/CDN providers, public technologies, and SPF/DMARC presence.
- **Method:** crt.sh certificate transparency search; standard DNS queries (A, MX, TXT, NS, CNAME) via public resolvers; RDAP lookups for IP registrant organisations; a normal HTTP GET of the target's own homepage. No login, no port scanning, no personal data.
- **Constraints:** crt.sh may rate-limit; failures are recorded per finding, not treated as fatal.

## Target's own public documents (COLLECT-007)

- **Used by:** `crawler/exposure/`.
- **Purpose:** Discover and extract operational facts (remote/device policy, headcount, office locations, named vendors, named staff, support contact patterns) that a target's own public documents disclose, to assess pretexting/phishing exposure.
- **Method:** the target's own sitemap.xml (falling back to same-domain homepage links) for discovery; a normal HTTP GET of each candidate PDF/DOCX/HTML page. No search engines, no login, no paywalled content.
- **Constraints:** requires the operator to assert authorisation for the exact domain before any request is made (see SECURITY.md). Respects robots.txt; identifies itself in the User-Agent; rate-limited; capped at a configurable number of documents per run (default 40, hard maximum 150). Retrieved passages are sent to the Anthropic API for structured extraction (DEC-003); embeddings for local retrieval stay on-machine.
