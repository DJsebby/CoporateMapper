import unittest
from unittest.mock import Mock, patch

from Leaks.Crt import CrtShSearch


class CrtShSearchTests(unittest.TestCase):
    def test_queries_the_supplied_domain_and_deduplicates_names(self):
        response = Mock(status_code=200)
        response.json.return_value = [
            {"name_value": "*.example.com\nwww.example.com\nAPI.EXAMPLE.COM"},
            {"name_value": "api.example.com"},
        ]

        with patch("Leaks.Crt.requests.get", return_value=response) as get:
            results = CrtShSearch(" Example.COM. ").fetch_subdomains()

        self.assertEqual(
            get.call_args.kwargs["params"],
            {"q": "%.example.com", "output": "json"},
        )
        self.assertEqual(
            results,
            ["api.example.com", "example.com", "www.example.com"],
        )

    def test_rejects_empty_domain(self):
        with self.assertRaisesRegex(ValueError, "domain must not be empty"):
            CrtShSearch(" . ")


if __name__ == "__main__":
    unittest.main()