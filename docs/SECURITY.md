# Security

Approved security requirements, privacy requirements, and defensive-use boundaries.

## Collected personal data (approved by the CEO, 2026-09-26)

- Collectors may retain all contact details they find (emails, phone numbers, social profiles) for testing and demonstration.
- Collected personal data must not be published: it stays on team members' machines and is not committed to git, shared publicly, or shown outside the team's demo.
- API keys (Bright Data, Apollo) are read from environment variables and must not be committed.
- Each team member uses their own Apollo account and key; runs are credit-capped.

## Public-document exposure assessment (COLLECT-007, approved by the CEO, 2026-09-26)

- The tool must not run against a domain unless the operator explicitly asserts authorisation for that exact domain (own org, or a consenting client specified by name). There is no default-authorised domain.
- Fetched documents and any local FAISS index/cache are not committed to git, shared publicly, or shown outside the team's demo (same rule as collected personal data, above).
- Retrieved passages are sent to the Anthropic API (per DEC-003) for structured extraction. This is the only third party document content is sent to; embeddings stay local. `ANTHROPIC_API_KEY` is read from the environment and never committed.
- Crawling identifies itself in the User-Agent, respects robots.txt, and rate-limits requests to the target's own site only.
- Every fetched document is also scanned deterministically (regex, not the LLM) for email addresses and linked domains, so a domain isn't missed just because it fell outside the LLM's fixed retrieval queries. Found emails/domains follow the same rule as other collected contact data (above): retained for the team's own use, never published.

Other security design has not yet been approved.
