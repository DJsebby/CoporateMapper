"""Offline tests for crawler.exposure.extract. No live LLM or network calls are made."""

import unittest

from crawler.exposure.extract import InstructorAnthropicClient, gather_passages
from crawler.exposure.schema import Fact, OperationalFacts, RetrievedPassage


def passage(text: str, url: str = "https://acme.example/policy") -> RetrievedPassage:
    return RetrievedPassage(text=text, source_url=url, document_type="html", location="page")


class FakeIndex:
    def __init__(self, results_by_query: dict[str, list[RetrievedPassage]]) -> None:
        self.results_by_query = results_by_query
        self.queries: list[str] = []

    def query(self, text: str, *, top_k: int = 5):
        self.queries.append(text)
        return self.results_by_query.get(text, [])[:top_k]


class GatherPassagesTests(unittest.TestCase):
    def test_dedupes_passages_seen_across_queries(self):
        shared = passage("Remote work is standard.")
        index = FakeIndex({"query one": [shared], "query two": [shared]})
        results = gather_passages(index, queries=["query one", "query two"])
        self.assertEqual(len(results), 1)

    def test_stops_at_max_passages(self):
        passages = [passage(f"text {i}", url=f"https://acme.example/{i}") for i in range(5)]
        index = FakeIndex({"q": passages})
        results = gather_passages(index, queries=["q"], top_k_per_query=5, max_passages=2)
        self.assertEqual(len(results), 2)

    def test_no_results_returns_empty(self):
        index = FakeIndex({})
        self.assertEqual(gather_passages(index, queries=["q"]), [])


class FakeMessagesClient:
    """Stands in for instructor.from_anthropic(...).messages, no network call."""

    def __init__(self, response: OperationalFacts) -> None:
        self.response = response
        self.calls: list[dict] = []

    class _Messages:
        def __init__(self, outer: "FakeMessagesClient") -> None:
            self._outer = outer

        def create(self, **kwargs):
            self._outer.calls.append(kwargs)
            return self._outer.response

    @property
    def messages(self):
        return self._Messages(self)


def sample_response() -> OperationalFacts:
    return OperationalFacts(
        remote_policy=Fact(value="remote", quote="fully remote", source_url="https://acme.example/policy", confidence="high"),
        device_policy=Fact.not_stated(),
        headcount_band=Fact.not_stated(),
    )


class InstructorAnthropicClientTests(unittest.TestCase):
    def test_extract_passes_passages_and_returns_response(self):
        fake_client = FakeMessagesClient(sample_response())
        client = InstructorAnthropicClient(client=fake_client)

        result = client.extract([passage("All staff work fully remote.")])

        self.assertEqual(result.remote_policy.value, "remote")
        [call] = fake_client.calls
        self.assertEqual(call["response_model"], OperationalFacts)
        self.assertIn("fully remote", call["messages"][0]["content"])
        self.assertIn("https://acme.example/policy", call["messages"][0]["content"])

    def test_extract_with_no_passages_skips_the_call(self):
        fake_client = FakeMessagesClient(sample_response())
        client = InstructorAnthropicClient(client=fake_client)

        result = client.extract([])

        self.assertEqual(result.remote_policy.value, "not_stated")
        self.assertEqual(fake_client.calls, [])


if __name__ == "__main__":
    unittest.main()
