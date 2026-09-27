"""Offline tests for crawler.exposure.index. No network calls, no embedding model download."""

import unittest

from crawler.exposure.fetch import NormalizedDocument, Section
from crawler.exposure.index import PassageIndex, chunk_document

VOCAB = ["remote", "vendor", "office"]


class FakeEmbedder:
    """Deterministic bag-of-words embedder; no model download, no network."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(text.lower().count(word)) for word in VOCAB] for text in texts]


class ChunkDocumentTests(unittest.TestCase):
    def test_short_section_produces_one_passage(self):
        doc = NormalizedDocument(
            url="https://acme.example/policy",
            document_type="html",
            sections=[Section(location="page", text="Staff work remote most days.")],
        )
        passages = chunk_document(doc)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0].source_url, "https://acme.example/policy")
        self.assertEqual(passages[0].document_type, "html")
        self.assertEqual(passages[0].location, "page")

    def test_long_section_splits_into_multiple_passages(self):
        text = " ".join(f"word{i}" for i in range(600))
        doc = NormalizedDocument(
            url="https://acme.example/report.pdf",
            document_type="pdf",
            sections=[Section(location="page 1", text=text)],
        )
        passages = chunk_document(doc, chunk_size=120, overlap=24)
        self.assertGreater(len(passages), 1)
        for passage in passages:
            self.assertEqual(passage.location, "page 1")

    def test_empty_section_skipped(self):
        doc = NormalizedDocument(
            url="https://acme.example/empty",
            document_type="html",
            sections=[Section(location="page", text="")],
        )
        self.assertEqual(chunk_document(doc), [])


class PassageIndexTests(unittest.TestCase):
    def test_query_returns_most_similar_passage(self):
        doc = NormalizedDocument(
            url="https://acme.example/mixed",
            document_type="html",
            sections=[
                Section(location="a", text="All staff work remote from home."),
                Section(location="b", text="We use Salesforce as our primary vendor tool."),
                Section(location="c", text="Our office is downtown."),
            ],
        )
        passages = chunk_document(doc, chunk_size=6000, overlap=0)
        index = PassageIndex(embedder=FakeEmbedder())
        index.build(passages)

        results = index.query("remote work policy", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("remote", results[0].text.lower())

    def test_query_with_no_passages_returns_empty(self):
        index = PassageIndex(embedder=FakeEmbedder())
        index.build([])
        self.assertEqual(index.query("anything"), [])


if __name__ == "__main__":
    unittest.main()
