"""Cross-language query expansion for lexical retrieval.

Expands Chinese academic queries with English keyword equivalents,
enabling lexical matching against English paper chunks.
No external API calls; this is a static dictionary-based helper.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# Chinese-to-English academic term mapping.
_CN_EN_MAP: dict[str, list[str]] = {
    "核心贡献": ["core", "contribution", "main contribution"],
    "贡献": ["contribution", "novelty", "main idea"],
    "方法": ["method", "approach", "framework", "algorithm", "propose"],
    "提出": ["propose", "proposed", "introduce", "method"],
    "模型": ["model", "architecture", "framework"],
    "实验": ["experiment", "evaluation", "result", "benchmark"],
    "结果": ["result", "performance", "evaluation"],
    "局限": ["limitation", "weakness", "challenge"],
    "不足": ["limitation", "weakness", "challenge"],
    "未来工作": ["future work", "direction", "improve", "extend"],
    "挑战": ["challenge", "open problem"],
    "改进": ["improve", "extend", "enhance"],
    "注意力": ["attention", "self-attention", "transformer"],
    "检索增强": ["retrieval", "augmented", "generation", "RAG"],
    "多智能体": ["multi-agent", "agent", "workflow", "supervisor"],
    "工作流": ["workflow", "pipeline", "agent workflow"],
    "研究": ["research", "study", "investigate"],
    "论文": ["paper", "study", "work"],
    "问题": ["problem", "issue", "question"],
    "解决": ["solve", "address", "tackle"],
    "性能": ["performance", "accuracy", "efficiency"],
    "效果": ["effectiveness", "performance", "result"],
    "对比": ["comparison", "compare", "versus"],
    "差异": ["difference", "distinction", "comparison"],
    "共同点": ["common", "shared", "similarity"],
    "组合": ["combine", "integrate", "fusion"],
    "方向": ["direction", "future work", "research direction"],
    "生成": ["generation", "generate", "generative"],
    "编码器": ["encoder", "encoding"],
    "解码器": ["decoder", "decoding"],
    "训练": ["training", "train", "learning"],
    "微调": ["fine-tune", "fine-tuning", "finetune"],
    "预训练": ["pre-train", "pre-training", "pretrain"],
    "知识图谱": ["knowledge graph", "KG"],
    "图神经网络": ["graph neural network", "GNN"],
    "联邦学习": ["federated learning", "federated"],
    "差分隐私": ["differential privacy", "privacy"],
    "自然语言处理": ["NLP", "natural language processing"],
    "深度学习": ["deep learning"],
    "机器学习": ["machine learning"],
    "强化学习": ["reinforcement learning"],
    "表示学习": ["representation learning"],
    "语义": ["semantic", "semantics"],
    "向量": ["vector", "embedding", "representation"],
    "嵌入": ["embedding", "representation"],
    "序列": ["sequence", "sequential"],
    "文本": ["text", "document"],
    "数据集": ["dataset", "benchmark", "corpus"],
    "评估": ["evaluation", "assessment", "metric"],
    "基线": ["baseline", "benchmark"],
    "消融": ["ablation", "ablation study"],
    "参数": ["parameter", "hyperparameter"],
    "优化": ["optimization", "optimize", "optimizer"],
    "损失函数": ["loss function", "loss"],
    "梯度": ["gradient", "gradient descent"],
    "收敛": ["convergence", "converge"],
    "过拟合": ["overfitting", "overfit"],
    "正则化": ["regularization", "regularize"],
    "注意力机制": ["attention mechanism", "attention", "self-attention"],
}


def _contains_chinese(text: str) -> bool:
    """Check if text contains Chinese characters."""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _extract_chinese_terms(text: str) -> list[str]:
    """Extract Chinese character sequences from text."""
    return re.findall(r"[\u4e00-\u9fff]+", text)


@dataclass
class QueryExpansionResult:
    original_query: str
    expanded_query: str
    expanded_terms: list[str] = field(default_factory=list)
    applied: bool = False
    reason: str = ""


def expand_query(query: str) -> QueryExpansionResult:
    """Expand a Chinese academic query with English keyword equivalents.

    Strategy:
    - Detect Chinese characters in query
    - Match Chinese substrings against _CN_EN_MAP (longest match first)
    - Append English equivalents to original query
    - English queries are not expanded
    - Empty queries are not expanded
    """
    if not query or not query.strip():
        return QueryExpansionResult(
            original_query=query,
            expanded_query=query,
            applied=False,
            reason="empty_query",
        )

    if not _contains_chinese(query):
        return QueryExpansionResult(
            original_query=query,
            expanded_query=query,
            applied=False,
            reason="no_chinese",
        )

    expanded_terms: list[str] = []
    seen_terms: set[str] = set()

    # Sort map keys by length (longest first) for greedy matching
    sorted_keys = sorted(_CN_EN_MAP.keys(), key=len, reverse=True)

    # Track which positions in the query have been matched
    matched_ranges: list[tuple[int, int]] = []

    for cn_term in sorted_keys:
        start = 0
        while True:
            idx = query.find(cn_term, start)
            if idx == -1:
                break
            end = idx + len(cn_term)
            # Check if this range overlaps with already matched ranges
            overlaps = False
            for ms, me in matched_ranges:
                if idx < me and end > ms:
                    overlaps = True
                    break
            if not overlaps:
                matched_ranges.append((idx, end))
                for en_term in _CN_EN_MAP[cn_term]:
                    if en_term.lower() not in seen_terms:
                        expanded_terms.append(en_term.lower())
                        seen_terms.add(en_term.lower())
            start = idx + 1

    if not expanded_terms:
        return QueryExpansionResult(
            original_query=query,
            expanded_query=query,
            applied=False,
            reason="no_matching_terms",
        )

    # Build expanded query: original + expanded English terms
    expanded_query = query + " " + " ".join(expanded_terms)

    return QueryExpansionResult(
        original_query=query,
        expanded_query=expanded_query,
        expanded_terms=expanded_terms,
        applied=True,
        reason="chinese_query_expanded",
    )


def should_expand_query(enabled: bool, mode: str) -> bool:
    """Return whether static query expansion should be applied."""
    return enabled and mode.strip().lower() == "static"
