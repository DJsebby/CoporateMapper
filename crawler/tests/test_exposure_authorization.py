"""Offline tests for crawler.exposure.authorization. No network calls are made."""

import unittest

from crawler.exposure.authorization import AuthorizationError, require_authorization


class RequireAuthorizationTests(unittest.TestCase):
    def test_missing_authorized_domain_raises(self):
        with self.assertRaises(AuthorizationError):
            require_authorization("acme.example", authorized_domain=None, confirmed=True)

    def test_missing_confirmation_raises(self):
        with self.assertRaises(AuthorizationError):
            require_authorization("acme.example", authorized_domain="acme.example", confirmed=False)

    def test_mismatched_domain_raises(self):
        with self.assertRaises(AuthorizationError):
            require_authorization("acme.example", authorized_domain="other.example", confirmed=True)

    def test_matching_domain_and_confirmation_passes(self):
        require_authorization("acme.example", authorized_domain="acme.example", confirmed=True)

    def test_scheme_and_www_ignored_when_matching(self):
        require_authorization(
            "acme.example", authorized_domain="https://www.acme.example/", confirmed=True
        )

    def test_case_insensitive_match(self):
        require_authorization("ACME.example", authorized_domain="acme.EXAMPLE", confirmed=True)


if __name__ == "__main__":
    unittest.main()
