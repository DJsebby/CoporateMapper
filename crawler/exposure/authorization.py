"""
Authorisation gate for COLLECT-007.

The exposure-assessment pipeline must not run against a domain unless the
operator explicitly asserts authorisation for that exact domain (their own
org, or a consenting client they name). There is no default-authorised
domain and no implicit "if unspecified, assume allowed" path.
"""

from __future__ import annotations


class AuthorizationError(RuntimeError):
    pass


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0]
    value = value.split(":", 1)[0]
    return value.rstrip(".").removeprefix("www.")


def require_authorization(
    target_domain: str, *, authorized_domain: str | None, confirmed: bool
) -> None:
    """
    Raise AuthorizationError unless the operator supplied a matching
    ``authorized_domain`` and set ``confirmed``. Call this before any
    network request is made.
    """
    if not authorized_domain or not confirmed:
        raise AuthorizationError(
            "Refusing to run: pass --authorized-domain <domain> naming the domain you are "
            "authorised to assess (your own org, or a named consenting client), plus --confirm, "
            "before this tool will make any request."
        )
    if normalize_domain(authorized_domain) != normalize_domain(target_domain):
        raise AuthorizationError(
            f"Refusing to run: --authorized-domain {authorized_domain!r} does not match "
            f"the target domain {target_domain!r}."
        )
