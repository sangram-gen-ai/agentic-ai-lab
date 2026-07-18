"""Local AI utility helpers (Step 6).

These are deterministic, offline-friendly utilities for the document pipeline:

- **summarize** — extractive summary (top-scoring sentences)
- **classify** — keyword scores against lab document categories
- **chunk** — sliding-window chunk preview (feeds Phase 4 RAG)

LLM-backed versions can later call Spring AI / Bedrock; this step stays local
so the FastAPI service is usable without Phase 2 running.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from app.config import Settings, get_settings

# Categories align with sample folders under documents/
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "resume": (
        "resume",
        "curriculum",
        "experience",
        "education",
        "skills",
        "employment",
        "linkedin",
        "bachelor",
        "master",
    ),
    "invoice": (
        "invoice",
        "bill",
        "amount due",
        "total due",
        "payment",
        "subtotal",
        "tax",
        "qty",
        "unit price",
    ),
    "contract": (
        "agreement",
        "contract",
        "party",
        "parties",
        "hereby",
        "terms",
        "obligations",
        "governing law",
        "signature",
    ),
    "healthcare": (
        "patient",
        "diagnosis",
        "clinical",
        "medical",
        "physician",
        "treatment",
        "hospital",
        "prescription",
        "symptom",
    ),
    "claim": (
        "claim",
        "policy",
        "coverage",
        "loss",
        "adjuster",
        "insured",
        "deductible",
        "incident",
        "settlement",
    ),
}

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass
class SummaryResult:
    summary: str
    sentence_count: int
    method: str


@dataclass
class ClassificationResult:
    label: str
    confidence: float
    scores: dict[str, float]
    method: str


@dataclass
class TextChunk:
    index: int
    text: str
    start: int
    end: int
    char_count: int


@dataclass
class ChunkPreviewResult:
    chunk_count: int
    chunk_size: int
    chunk_overlap: int
    chunks: list[TextChunk]


class AiUtilsService:
    def __init__(self, settings: Settings) -> None:
        self._chunk_size = settings.chunk_size
        self._chunk_overlap = settings.chunk_overlap
        self._max_sentences = settings.summarize_max_sentences

    def summarize(self, text: str, max_sentences: int | None = None) -> SummaryResult:
        cleaned = text.strip()
        if not cleaned:
            return SummaryResult(summary="", sentence_count=0, method="extractive")

        limit = max(1, max_sentences or self._max_sentences)
        sentences = [s.strip() for s in _SENTENCE_RE.split(cleaned) if s.strip()]
        if not sentences:
            return SummaryResult(summary=cleaned[:280], sentence_count=0, method="extractive")
        if len(sentences) <= limit:
            return SummaryResult(
                summary=" ".join(sentences),
                sentence_count=len(sentences),
                method="extractive",
            )

        # Score sentences by shared content words (classic extractive heuristic)
        doc_words = _WORD_RE.findall(cleaned.lower())
        freq = Counter(w for w in doc_words if len(w) > 2)
        ranked: list[tuple[float, int, str]] = []
        for idx, sentence in enumerate(sentences):
            words = _WORD_RE.findall(sentence.lower())
            if not words:
                score = 0.0
            else:
                score = sum(freq.get(w, 0) for w in words) / len(words)
            # Slight preference for earlier sentences (title/lead bias)
            score += max(0.0, 0.15 - idx * 0.01)
            ranked.append((score, idx, sentence))

        top = sorted(ranked, key=lambda item: (-item[0], item[1]))[:limit]
        ordered = [s for _, _, s in sorted(top, key=lambda item: item[1])]
        return SummaryResult(
            summary=" ".join(ordered),
            sentence_count=len(ordered),
            method="extractive",
        )

    def classify(self, text: str) -> ClassificationResult:
        lowered = text.lower()
        if not lowered.strip():
            return ClassificationResult(
                label="unknown",
                confidence=0.0,
                scores={name: 0.0 for name in CATEGORY_KEYWORDS},
                method="keyword",
            )

        raw_scores: dict[str, float] = {}
        for label, keywords in CATEGORY_KEYWORDS.items():
            hits = sum(1.0 for kw in keywords if kw in lowered)
            raw_scores[label] = hits / len(keywords)

        best_label = max(raw_scores, key=raw_scores.get)
        best_score = raw_scores[best_label]
        if best_score <= 0.0:
            return ClassificationResult(
                label="unknown",
                confidence=0.0,
                scores=raw_scores,
                method="keyword",
            )

        return ClassificationResult(
            label=best_label,
            confidence=round(min(1.0, best_score), 4),
            scores={k: round(v, 4) for k, v in raw_scores.items()},
            method="keyword",
        )

    def chunk(
        self,
        text: str,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> ChunkPreviewResult:
        size = chunk_size if chunk_size is not None else self._chunk_size
        overlap = chunk_overlap if chunk_overlap is not None else self._chunk_overlap

        if size < 1:
            raise ValueError("chunk_size must be >= 1")
        if overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if overlap >= size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        content = text.strip()
        if not content:
            return ChunkPreviewResult(
                chunk_count=0,
                chunk_size=size,
                chunk_overlap=overlap,
                chunks=[],
            )

        step = size - overlap
        chunks: list[TextChunk] = []
        start = 0
        index = 0
        length = len(content)
        while start < length:
            end = min(start + size, length)
            piece = content[start:end]
            chunks.append(
                TextChunk(
                    index=index,
                    text=piece,
                    start=start,
                    end=end,
                    char_count=len(piece),
                )
            )
            if end >= length:
                break
            start += step
            index += 1

        return ChunkPreviewResult(
            chunk_count=len(chunks),
            chunk_size=size,
            chunk_overlap=overlap,
            chunks=chunks,
        )


@lru_cache
def get_ai_utils_service() -> AiUtilsService:
    return AiUtilsService(get_settings())
