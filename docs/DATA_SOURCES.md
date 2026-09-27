# Data Sources

## Serper Search API

The name-recon utility uses Serper's Google Search API only when explicitly run. It sends one query for the supplied full name and company and/or role, and requests at most 10 results. It returns the API's title, result URL, and snippet; it does not fetch or scrape result pages.

The utility requires `SERPER_API_KEY` in the process environment or local `.env`. It sends the key in the `X-API-KEY` request header, not the URL. See [Serper](https://serper.dev/).

The generic helper uses the same API settings. The current email example passes an address as an exact quoted query; the helper returns Serper's JSON response and does not fetch result pages.

Do not add browser scraping, CAPTCHA bypass, proxy rotation, or other anti-bot evasion to this source.
