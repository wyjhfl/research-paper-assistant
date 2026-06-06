"""Lexical retrieval / hybrid scoring for RAG.

Provides BM25-style lexical scoring that works without external APIs.
When vector scores are near-zero (e.g. local hash embedding), lexical
scores become the primary ranking signal, making strict RAG usable.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass


# ── Stop words (English) ──────────────────────────────────────────
_STOP_WORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "of", "in", "to",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out", "off",
    "over", "under", "again", "further", "then", "once", "and", "but", "or",
    "nor", "not", "so", "yet", "both", "either", "neither", "each", "every",
    "all", "any", "few", "more", "most", "other", "some", "such", "no",
    "only", "own", "same", "than", "too", "very", "just", "because",
    "if", "when", "where", "how", "what", "which", "who", "whom", "this",
    "that", "these", "those", "it", "its", "he", "she", "they", "them",
    "we", "you", "i", "me", "my", "your", "his", "her", "our", "their",
}

# Chinese stop words (common function words)
_CN_STOP_WORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会",
    "着", "没有", "看", "好", "自己", "这", "他", "她", "它", "们",
    "那", "被", "从", "把", "让", "对", "而", "但", "与", "或", "及",
    "等", "所", "以", "之", "其", "可", "能", "还", "则", "此",
}


def tokenize(text: str) -> list[str]:
    """Tokenize text into a list of tokens.

    - English: lowercase, split on non-alphanumeric
    - Chinese: bigram character pairs
    - Remove stop words
    - Keep tokens with length >= 2
    """
    tokens: list[str] = []
    lowered = text.lower()

    # Extract English/ASCII words
    ascii_words = re.findall(r"[a-z0-9]+", lowered)
    for w in ascii_words:
        if len(w) >= 2 and w not in _STOP_WORDS:
            tokens.append(w)

    # Extract Chinese bigrams
    non_ascii = re.sub(r"[a-z0-9\s]", "", lowered)
    for i in range(len(non_ascii) - 1):
        bigram = non_ascii[i] + non_ascii[i + 1]
        if bigram not in _CN_STOP_WORDS:
            tokens.append(bigram)
    if len(non_ascii) == 1 and non_ascii not in _CN_STOP_WORDS:
        tokens.append(non_ascii[0])

    return tokens


def _token_set(text: str) -> set[str]:
    return set(tokenize(text))


def _has_exact_phrase(query: str, text: str) -> bool:
    """Check if any 3+ word subsequence of query appears in text."""
    q_tokens = tokenize(query)
    if len(q_tokens) < 2:
        return False
    text_lower = text.lower()
    # Check 2-grams and 3-grams from query tokens
    for n in (3, 2):
        for i in range(len(q_tokens) - n + 1):
            phrase = " ".join(q_tokens[i : i + n])
            if phrase in text_lower:
                return True
    return False


@dataclass
class LexicalScoreResult:
    score: float
    query_token_recall: float
    overlap_count: int
    has_phrase_match: bool


def compute_lexical_score(
    query: str,
    chunk_text: str,
    title: str = "",
) -> LexicalScoreResult:
    """Compute a lexical relevance score between query and chunk text.

    Scoring components:
    1. Query token recall: fraction of query tokens found in chunk
    2. Term frequency boost: log(1 + hit_count) / log(1 + chunk_token_count)
    3. Title bonus: +0.1 if query tokens appear in title
    4. Exact phrase bonus: +0.1 if multi-word phrase from query is in chunk

    Score is clamped to [0, 1].
    """
    query_tokens = _token_set(query)
    if not query_tokens:
        return LexicalScoreResult(
            score=0.0, query_token_recall=0.0,
            overlap_count=0, has_phrase_match=False,
        )

    chunk_tokens = _token_set(chunk_text)
    if not chunk_tokens:
        return LexicalScoreResult(
            score=0.0, query_token_recall=0.0,
            overlap_count=0, has_phrase_match=False,
        )

    overlap = query_tokens & chunk_tokens
    overlap_count = len(overlap)
    recall = overlap_count / len(query_tokens)

    # Term frequency normalization
    chunk_token_list = tokenize(chunk_text)
    hit_count = sum(1 for t in chunk_token_list if t in query_tokens)
    tf_norm = math.log1p(hit_count) / math.log1p(max(len(chunk_token_list), 1))

    # Base score: weighted combination of recall and TF
    score = 0.6 * recall + 0.4 * tf_norm

    # Title bonus
    if title:
        title_tokens = _token_set(title)
        if query_tokens & title_tokens:
            score += 0.1

    # Exact phrase bonus
    has_phrase = _has_exact_phrase(query, chunk_text)
    if has_phrase:
        score += 0.1

    score = max(0.0, min(1.0, score))

    return LexicalScoreResult(
        score=round(score, 4),
        query_token_recall=round(recall, 4),
        overlap_count=overlap_count,
        has_phrase_match=has_phrase,
    )


def is_local_embedding_provider() -> bool:
    """Check if current embedding provider is local (non-semantic)."""
    from ..config import settings
    return settings.EMBEDDING_PROVIDER == "local"


def compute_hybrid_score(
    vector_score: float,
    lexical_score: float,
    vector_weight: float = 0.7,
    lexical_weight: float = 0.3,
) -> float:
    """Compute hybrid score from vector and lexical scores.

    Strategy:
    - If local embedding (vector scores ~0): use lexical score as primary
    - If real embedding: use weighted hybrid
    """
    if is_local_embedding_provider():
        # When vector scores are meaningless, lexical is primary
        # Still blend a tiny bit of vector score for tiebreaking
        return round(0.9 * lexical_score + 0.1 * vector_score, 4)
    else:
        return round(vector_weight * vector_score + lexical_weight * lexical_score, 4)


def determine_retrieval_mode(
    vector_score: float,
    lexical_score: float,
) -> str:
    """Determine the effective retrieval mode for a result."""
    if is_local_embedding_provider():
        if lexical_score > 0:
            return "lexical"
        return "vector"
    if vector_score > 0.01 and lexical_score > 0:
        return "hybrid"
    if vector_score > 0.01:
        return "vector"
    if lexical_score > 0:
        return "lexical"
    return "vector"


def compute_lexical_score_with_expansion(
    query: str,
    chunk_text: str,
    title: str = "",
) -> tuple[LexicalScoreResult, "QueryExpansionResult"]:
    """Compute lexical score with query expansion support.

    If the query contains Chinese characters, expands with English terms
    and uses the expanded query for lexical scoring.

    Returns (lexical_score_result, expansion_result).
    """
    from .query_expansion import expand_query, QueryExpansionResult

    expansion = expand_query(query)

    if expansion.applied:
        # Use expanded query for scoring (includes English equivalents)
        lex_result = compute_lexical_score(expansion.expanded_query, chunk_text, title)
    else:
        lex_result = compute_lexical_score(query, chunk_text, title)

    return lex_result, expansion
