"""Bounded, public-only providers for the shared employee enrichment engine.

Search budgets and page-attempt reservations belong to the persistent engine.
This module never retries search requests and never retains result snippets.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import os
from queue import Queue, Empty
import re
import socket
import ssl
import time
import threading
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from cli_support import CommandError
from crawler.models import PageDocument


class SourceError(CommandError):
    """Safe, actionable error text; never include remote response bodies."""


class ProviderQuotaError(SourceError):
    """Search must stop until the operator configures available allowance."""


def build_query(name: str, company: str = "") -> str:
    def phrase(value):
        # Remove embedded operators/quotes while keeping the complete phrase.
        if not isinstance(value, str):
            raise SourceError("Search names and organisations must be text.")
        return " ".join(value.replace('"', ' ').replace('\\', ' ').split())[:200]
    name, company = phrase(name), phrase(company)
    if not name:
        raise SourceError("An employee name is required for search.")
    return " ".join([f'"{name}"', *([f'"{company}"'] if company else []), "Australia"])


def public_url(url: str) -> str:
    """Validate syntax separately from DNS, including all redirect targets."""
    if not isinstance(url, str) or len(url) > 2048 or re.search(r"[\x00-\x20\x7f]", url):
        raise SourceError("The source URL is invalid.")
    try:
        parts = urlsplit(url)
        port = parts.port
        host = parts.hostname
        if parts.scheme not in {"http", "https"} or not host or parts.username is not None or parts.password is not None:
            raise ValueError()
        if port is not None and port != (443 if parts.scheme == "https" else 80):
            raise ValueError()
        host.encode("idna")
        if "%" in host or host.rstrip(".").lower() in {"localhost", "localhost.localdomain"}:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise SourceError("Only public HTTP(S) source URLs on standard ports are supported.") from None
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


_RESOLVER_SLOTS = threading.BoundedSemaphore(4)


def resolve_public(url: str, timeout: float = 5.0) -> tuple[str, int, str]:
    """Resolve once, reject mixed/private answers, and return an IP to pin."""
    parts = urlsplit(public_url(url))
    host = parts.hostname.encode("idna").decode("ascii")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        literal = ipaddress.ip_address(host)
        addresses = [str(literal)]
    except ValueError:
        deadline = time.monotonic() + timeout
        if not _RESOLVER_SLOTS.acquire(timeout=max(0, timeout)):
            raise SourceError("Source DNS lookup capacity is unavailable; page skipped.")
        result = Queue(maxsize=1)
        def lookup():
            try:
                result.put((True, socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)))
            except Exception:
                result.put((False, None))
            finally:
                _RESOLVER_SLOTS.release()
        # OS DNS cannot be cancelled safely. Daemon workers prevent a stuck
        # lookup from blocking process shutdown; slots bound abandoned work.
        worker = threading.Thread(target=lookup, daemon=True, name="public-source-dns")
        try:
            worker.start()
        except RuntimeError:
            _RESOLVER_SLOTS.release()
            raise SourceError("Source DNS lookup could not start.") from None
        try:
            success, rows = result.get(timeout=max(0.001, deadline-time.monotonic()))
            if not success:
                raise SourceError("Source DNS lookup failed or timed out.")
            addresses = list(dict.fromkeys(row[4][0] for row in rows))
        except Empty:
            raise SourceError("Source DNS lookup failed or timed out.") from None
    if not addresses:
        raise SourceError("The source has no public address.")
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            raise SourceError("Source DNS returned an invalid address.") from None
        if not parsed.is_global or parsed.is_multicast or parsed.is_reserved or parsed.is_unspecified or parsed.is_loopback or parsed.is_link_local:
            raise SourceError("Private, reserved, and local network sources are blocked.")
    return host, port, addresses[0]


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, *, secure, timeout):
        super().__init__(host, port, timeout=timeout)
        self._address, self._secure = address, secure

    def connect(self):
        # Connect directly to the validated literal. No second hostname lookup,
        # proxy environment, or redirect library can change the destination.
        family = socket.AF_INET6 if ":" in self._address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        self.sock = sock
        sock.settimeout(self.timeout)
        try:
            sock.connect((self._address, self.port))
            if self._secure:
                self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host, do_handshake_on_connect=False)
                self.sock.do_handshake()
        except BaseException:
            sock.close()
            raise


class LiveSources:
    USER_AGENT = "CorporateMapper/1.0"
    MAX_BYTES = 2_000_000
    MAX_REDIRECTS = 3
    TIMEOUT = 10
    PAGE_DEADLINE = 45

    def __init__(self, api_key: str | None = None):
        self.api_key = os.getenv("SERPER_API_KEY", "") if api_key is None else api_key
        self._robots = {}
        self._last_request = {}

    def close(self):
        pass

    def check_search_ready(self):
        if not self.api_key or self.api_key.lower().startswith(("your_", "replace", "placeholder")):
            raise SourceError("Set SERPER_API_KEY before requesting a live search.")

    def search(self, name: str, company: str = "") -> list[dict]:
        self.check_search_ready()
        query = build_query(name, company)
        connection = http.client.HTTPSConnection("google.serper.dev", timeout=15)
        try:
            connection.request("POST", "/search", json.dumps({"q": query, "num": 10, "gl": "au"}),
                               {"X-API-KEY": self.api_key, "Content-Type": "application/json"})
            response = connection.getresponse()
            body = response.read(self.MAX_BYTES + 1)
            if response.status in {402, 429}:
                raise ProviderQuotaError("Serper quota or rate limit reached; search stopped.")
            if response.status >= 400:
                raise SourceError(f"Serper returned HTTP {response.status}; no retry was made.")
            if len(body) > self.MAX_BYTES:
                raise SourceError("Serper returned an oversized response.")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError()
            # Serper credits describes request cost, not remaining balance.
            # Only the durable operator allowance and explicit quota errors
            # can stop future searches; do not infer a balance here.
            error = str(data.get("message", data.get("error", ""))).casefold()
            if any(word in error for word in ("quota", "credit", "rate limit", "resource_exhausted")):
                raise ProviderQuotaError("Serper reports an exhausted search allowance.")
            if data.get("error"):
                raise SourceError("Serper rejected the search; no retry was made.")
            results = data.get("organic", [])
            if not isinstance(results, list):
                raise ValueError()
            output, seen = [], set()
            for item in results[:10]:
                if not isinstance(item, dict):
                    continue
                try:
                    url = public_url(item.get("link"))
                except SourceError:
                    continue
                if url not in seen:
                    seen.add(url)
                    # Search titles/snippets can contain personal information;
                    # keep only the URL and hostname as the discovery record.
                    output.append({"url": url, "source_name": urlsplit(url).hostname})
            return output
        except SourceError:
            raise
        except (OSError, http.client.HTTPException):
            raise SourceError("Serper request failed or timed out; the attempt was consumed.") from None
        except (ValueError, TypeError, UnicodeError):
            raise SourceError("Serper returned an unreadable response; no retry was made.") from None
        finally:
            connection.close()

    def _request(self, url: str, deadline: float, max_bytes: int | None = None):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceError("Source request time limit reached.")
        host, port, address = resolve_public(url, timeout=min(5, remaining))
        parts = urlsplit(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceError("Source request time limit reached.")
        connection = _PinnedConnection(host, port, address, secure=parts.scheme == "https", timeout=min(self.TIMEOUT, remaining))
        def expire():
            # A wall-clock deadline also interrupts slow headers/body dribbles;
            # socket inactivity timeouts alone do not limit total duration.
            active = connection.sock
            if active is not None:
                try:
                    active.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                active.close()
        watchdog = threading.Timer(remaining, expire)
        watchdog.daemon = True
        watchdog.start()
        try:
            path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
            connection.request("GET", path, headers={"User-Agent": self.USER_AGENT,
                               "Accept": "text/html,application/xhtml+xml,application/ld+json,application/json,text/plain;q=0.5",
                               "Accept-Encoding": "identity", "Connection": "close"})
            response = connection.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            limit = self.MAX_BYTES if max_bytes is None else max_bytes
            if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                raise SourceError("Compressed source responses are unsupported.")
            expected_length = int(headers["content-length"]) if headers.get("content-length") else None
            if expected_length is not None and (expected_length < 0 or expected_length > limit):
                raise SourceError("Source response exceeds the size limit.")
            body = bytearray()
            while len(body) <= limit:
                if time.monotonic() >= deadline:
                    raise SourceError("Source response exceeded the time limit.")
                if connection.sock is not None:
                    connection.sock.settimeout(min(self.TIMEOUT, max(0.001, deadline - time.monotonic())))
                block = response.read1(min(65536, limit + 1 - len(body)))
                if not block:
                    break
                body.extend(block)
            if len(body) > limit:
                raise SourceError("Source response exceeds the size limit.")
            if time.monotonic() >= deadline:
                raise SourceError("Source response exceeded the time limit.")
            if expected_length is not None and len(body) != expected_length:
                raise SourceError("Source response ended before its declared length.")
            return response.status, headers, bytes(body)
        except SourceError:
            raise
        except (OSError, http.client.HTTPException):
            raise SourceError("Public source request failed or timed out.") from None
        except (ValueError, UnicodeError):
            raise SourceError("Public source returned invalid response metadata.") from None
        finally:
            watchdog.cancel()
            connection.close()

    def _redirected(self, url: str, deadline: float, *, robots=False):
        current = public_url(url)
        for hop in range(self.MAX_REDIRECTS + 1):
            if not robots:
                self._check_robots(current, deadline)
            status, headers, body = self._request(current, deadline, 256_000 if robots else None)
            if status in {301, 302, 303, 307, 308}:
                if hop >= self.MAX_REDIRECTS or not headers.get("location"):
                    raise SourceError("Source redirect limit reached or target missing.")
                try:
                    current = public_url(urljoin(current, headers["location"]))
                except ValueError:
                    raise SourceError("Source redirect target is invalid.") from None
                continue
            return current, status, headers, body
        raise SourceError("Source redirect limit reached.")

    def _check_robots(self, url: str, deadline: float):
        parts = urlsplit(url)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        if origin not in self._robots:
            _, status, headers, body = self._redirected(origin + "/robots.txt", deadline, robots=True)
            parser = RobotFileParser()
            if status in {404, 410}:
                parser.parse([])
            elif status == 200:
                media = headers.get("content-type", "").split(";",1)[0].strip().lower()
                if (media and media not in {"text/plain", "text/x-robots", "application/octet-stream"}) or body.lstrip().startswith(b"<"):
                    raise SourceError("Robots policy returned an unsupported document; page skipped.")
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
            else:
                raise SourceError("Robots policy unavailable or access denied; page skipped.")
            self._robots[origin] = parser
        parser = self._robots[origin]
        if not parser.can_fetch(self.USER_AGENT, url):
            raise SourceError("Robots policy disallows this source page.")
        delay = max(1, parser.crawl_delay(self.USER_AGENT) or 0)
        rate = parser.request_rate(self.USER_AGENT)
        if rate and rate.requests:
            delay = max(delay, rate.seconds / rate.requests)
        wait = self._last_request.get(origin, 0) + delay - time.monotonic()
        if wait > 0:
            if wait > 15 or time.monotonic() + wait >= deadline:
                raise SourceError("Source crawl delay exceeds this request allowance.")
            time.sleep(wait)
        self._last_request[origin] = time.monotonic()

    def fetch(self, url: str) -> PageDocument:
        original = public_url(url)
        final, status, headers, body = self._redirected(original, time.monotonic() + self.PAGE_DEADLINE)
        if not 200 <= status < 300:
            raise SourceError(f"Public source returned HTTP {status}; page skipped.")
        media = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media not in {"text/html", "application/xhtml+xml", "application/ld+json", "application/json"}:
            raise SourceError("Public source content type is unsupported.")
        if "noindex" in headers.get("x-robots-tag", "").casefold() or "noai" in headers.get("x-robots-tag", "").casefold():
            raise SourceError("Source response requests exclusion from collection.")
        text = body.decode("utf-8", errors="replace")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser") if "html" in media else None
        if soup:
            robots = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
            if robots and any(token in str(robots.get("content", "")).lower() for token in ("noindex", "noai", "none")):
                raise SourceError("Source page requests exclusion from collection.")
            if soup.select('input[type="password"], .g-recaptcha, #challenge-form'):
                raise SourceError("Source requires authentication or an access challenge; page skipped.")
        structured = []
        payloads = [str(node.string or "") for node in soup.find_all("script", type="application/ld+json")] if soup else [text]
        for payload in payloads:
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, (list, dict)):
                    structured.append(parsed)
            except (ValueError, RecursionError):
                continue
        return PageDocument(url=original, final_url=final, status_code=status, content_type=media,
                            fetched_at=datetime.now(timezone.utc), html=text if soup else "",
                            title=soup.title.get_text(" ", strip=True)[:200] if soup and soup.title else urlsplit(final).hostname,
                            text="", structured_data=structured,
                            content_hash=hashlib.sha256(body).hexdigest())
