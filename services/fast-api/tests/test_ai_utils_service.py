"""Unit tests for the local AI utilities: summarize, classify, chunk.

Pure logic, no external services — constructs AiUtilsService directly with
explicit Settings rather than depending on the process-wide singleton.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services.ai_utils import AiUtilsService


@pytest.fixture()
def svc() -> AiUtilsService:
    return AiUtilsService(Settings())


class TestSummarize:
    def test_short_text_returns_all_sentences_unchanged(self, svc: AiUtilsService):
        text = "One sentence. Two sentence."
        result = svc.summarize(text, max_sentences=3)
        assert result.sentence_count == 2
        assert "One sentence." in result.summary
        assert "Two sentence." in result.summary

    def test_long_text_is_capped_at_max_sentences(self, svc: AiUtilsService):
        text = " ".join(f"Sentence number {i} has some content." for i in range(10))
        result = svc.summarize(text, max_sentences=3)
        assert result.sentence_count == 3
        assert result.method == "extractive"

    def test_empty_text_returns_empty_summary(self, svc: AiUtilsService):
        result = svc.summarize("   ", max_sentences=3)
        assert result.summary == ""
        assert result.sentence_count == 0

    def test_uses_configured_default_when_max_sentences_not_given(self, svc: AiUtilsService):
        text = " ".join(f"Sentence {i} here now." for i in range(10))
        result = svc.summarize(text)
        assert result.sentence_count == svc._max_sentences  # default from Settings


class TestClassify:
    def test_invoice_like_text_is_classified_as_invoice(self, svc: AiUtilsService):
        text = "Invoice total due is one hundred dollars. Please pay the subtotal and tax."
        result = svc.classify(text)
        assert result.label == "invoice"
        assert result.confidence > 0
        assert result.method == "keyword"

    def test_resume_like_text_is_classified_as_resume(self, svc: AiUtilsService):
        text = "Experience: Software Engineer. Education: Bachelor of Science. Skills: Python."
        result = svc.classify(text)
        assert result.label == "resume"

    def test_text_with_no_keyword_matches_is_unknown(self, svc: AiUtilsService):
        result = svc.classify("The sky is blue and birds fly south for the winter.")
        assert result.label == "unknown"
        assert result.confidence == 0.0

    def test_empty_text_is_unknown(self, svc: AiUtilsService):
        result = svc.classify("   ")
        assert result.label == "unknown"
        assert all(v == 0.0 for v in result.scores.values())


class TestChunk:
    def test_chunk_overlap_math(self, svc: AiUtilsService):
        text = "abcdefghijklmnopqrstuvwxyz"
        result = svc.chunk(text, chunk_size=10, chunk_overlap=3)
        assert result.chunk_count == 4
        assert [c.text for c in result.chunks] == [
            "abcdefghij",
            "hijklmnopq",
            "opqrstuvwx",
            "vwxyz",
        ]
        # Consecutive chunks actually overlap by the configured amount.
        assert result.chunks[0].text[-3:] == result.chunks[1].text[:3]

    def test_chunk_smaller_than_text_produces_one_chunk(self, svc: AiUtilsService):
        result = svc.chunk("short text", chunk_size=1000, chunk_overlap=0)
        assert result.chunk_count == 1
        assert result.chunks[0].text == "short text"

    def test_empty_text_produces_no_chunks(self, svc: AiUtilsService):
        result = svc.chunk("   ", chunk_size=10, chunk_overlap=2)
        assert result.chunk_count == 0
        assert result.chunks == []

    def test_rejects_overlap_greater_or_equal_to_size(self, svc: AiUtilsService):
        with pytest.raises(ValueError, match="overlap"):
            svc.chunk("some text", chunk_size=10, chunk_overlap=10)

    def test_rejects_chunk_size_below_one(self, svc: AiUtilsService):
        with pytest.raises(ValueError, match="chunk_size"):
            svc.chunk("some text", chunk_size=0, chunk_overlap=0)

    def test_rejects_negative_overlap(self, svc: AiUtilsService):
        with pytest.raises(ValueError, match="overlap"):
            svc.chunk("some text", chunk_size=10, chunk_overlap=-1)
