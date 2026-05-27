from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, init_db
from app.models import Paper, PaperChunk, Idea, IdeaSource
from app.services.ai_provider import get_embedding_provider

DEMO_PAPERS = [
    {
        "title": "Attention Is All You Need: A Revisit of Transformer Architecture",
        "filename": "demo_transformer.pdf",
        "file_path": "storage/demo/demo_transformer.pdf",
        "chunks": [
            {
                "chunk_index": 0,
                "page_start": 1,
                "page_end": 2,
                "section_title": "Introduction",
                "text": (
                    "The dominant sequence transduction models are based on complex recurrent "
                    "or convolutional neural networks that include an encoder and a decoder. "
                    "The best performing models also connect the encoder and decoder through an "
                    "attention mechanism. We propose a new simple network architecture, the "
                    "Transformer, based solely on attention mechanisms, dispensing with recurrence "
                    "and convolutions entirely. The Transformer uses multi-head self-attention to "
                    "capture dependencies between tokens in parallel, enabling significantly faster "
                    "training compared to recurrent architectures."
                ),
            },
            {
                "chunk_index": 1,
                "page_start": 2,
                "page_end": 4,
                "section_title": "Self-Attention Mechanism",
                "text": (
                    "An attention function can be described as mapping a query and a set of "
                    "key-value pairs to an output, where the query, keys, values, and output "
                    "are all vectors. The output is computed as a weighted sum of the values, "
                    "where the weight assigned to each value is computed by a compatibility "
                    "function of the query with the corresponding key. We call our particular "
                    "attention 'Scaled Dot-Product Attention'. The input consists of queries and "
                    "keys of dimension dk, and values of dimension dv. We compute the dot "
                    "products of the query with all keys, divide each by sqrt(dk), and apply "
                    "a softmax function to obtain the weights on the values."
                ),
            },
            {
                "chunk_index": 2,
                "page_start": 4,
                "page_end": 6,
                "section_title": "Multi-Head Attention",
                "text": (
                    "Instead of performing a single attention function with dmodel-dimensional "
                    "keys, values and queries, it is found beneficial to project the queries, "
                    "keys and values h times with different, learned linear projections to dk, "
                    "dk and dv dimensions, respectively. On each of these projected versions of "
                    "queries, keys and values, we then perform the attention function in parallel, "
                    "yielding dv-dimensional output values. These are concatenated and once again "
                    "projected, resulting in the final values. Multi-head attention allows the "
                    "model to jointly attend to information from different representation "
                    "subspaces at different positions."
                ),
            },
            {
                "chunk_index": 3,
                "page_start": 6,
                "page_end": 8,
                "section_title": "Positional Encoding",
                "text": (
                    "Since the Transformer model contains no recurrence and no convolution, "
                    "in order for the model to make use of the order of the sequence, we must "
                    "inject some information about the relative or absolute position of the "
                    "tokens in the sequence. To this end, we add 'positional encodings' to the "
                    "input embeddings at the bottoms of the encoder and decoder stacks. The "
                    "positional encoding dimension is the same as the embedding dimension so "
                    "that the two can be summed. We use sine and cosine functions of different "
                    "frequencies for positional encoding."
                ),
            },
            {
                "chunk_index": 4,
                "page_start": 8,
                "page_end": 10,
                "section_title": "Training and Results",
                "text": (
                    "We trained the Transformer on the WMT 2014 English-to-German and "
                    "English-to-French translation tasks. On English-to-German, the Transformer "
                    "(big) model achieves 28.4 BLEU, improving over the existing best results "
                    "by over 2 BLEU. On English-to-French, the model achieves a new single-model "
                    "state-of-the-art BLEU score of 41.0. The Transformer requires significantly "
                    "less computation to train than architectures based on recurrent or "
                    "convolutional layers. The parallelizability of self-attention enables "
                    "efficient training on modern hardware such as GPUs and TPUs."
                ),
            },
        ],
    },
    {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "filename": "demo_rag.pdf",
        "file_path": "storage/demo/demo_rag.pdf",
        "chunks": [
            {
                "chunk_index": 0,
                "page_start": 1,
                "page_end": 2,
                "section_title": "Introduction",
                "text": (
                    "Large pre-trained language models have been shown to store factual "
                    "knowledge in their parameters. However, their ability to access and "
                    "precisely manipulate knowledge is limited, leading to hallucination and "
                    "unreliable generation. We explore a general-purpose fine-tuning approach "
                    "called Retrieval-Augmented Generation (RAG), which combines pre-trained "
                    "parametric memory with non-parametric memory through a retrieval mechanism. "
                    "RAG models can access knowledge from an external document store, reducing "
                    "hallucination and improving factual accuracy."
                ),
            },
            {
                "chunk_index": 1,
                "page_start": 2,
                "page_end": 4,
                "section_title": "RAG Architecture",
                "text": (
                    "RAG consists of two components: a retriever and a generator. The retriever "
                    "uses a dense vector index to find relevant documents from a knowledge base. "
                    "Specifically, it employs a dual-encoder architecture where the query encoder "
                    "produces a dense representation of the input, and the document encoder "
                    "produces representations of passages. The generator is a seq2seq model "
                    "conditioned on the retrieved documents. We consider two RAG formulations: "
                    "RAG-Sequence, which uses the same retrieved document across the entire "
                    "generation, and RAG-Token, which can use different documents per token."
                ),
            },
            {
                "chunk_index": 2,
                "page_start": 4,
                "page_end": 6,
                "section_title": "Dense Passage Retrieval",
                "text": (
                    "The retrieval component of RAG is based on Dense Passage Retrieval (DPR), "
                    "which uses two BERT-based encoders to encode the query and the passage "
                    "separately into dense vectors. The relevance score of a passage given a "
                    "query is computed as the dot product of their embeddings. DPR is trained "
                    "using in-batch negatives and hard negatives from BM25. The index is built "
                    "offline by encoding all passages, and retrieval is performed via approximate "
                    "nearest neighbor search using FAISS or similar libraries."
                ),
            },
            {
                "chunk_index": 3,
                "page_start": 6,
                "page_end": 8,
                "section_title": "Evaluation and Results",
                "text": (
                    "We evaluate RAG on three open-domain question answering tasks: Natural "
                    "Questions, TriviaQA, and WebQuestions. RAG achieves state-of-the-art "
                    "results on all three benchmarks, outperforming both parametric seq2seq "
                    "models and task-specific retrieval-augmented approaches. RAG also "
                    "outperforms the retrieved documents alone, demonstrating the value of "
                    "generation conditioned on retrieval. The non-parametric memory can be "
                    "easily updated by replacing the document index without retraining the model."
                ),
            },
        ],
    },
    {
        "title": "Multi-Agent Research Workflow: Collaborative AI for Scientific Discovery",
        "filename": "demo_multi_agent.pdf",
        "file_path": "storage/demo/demo_multi_agent.pdf",
        "chunks": [
            {
                "chunk_index": 0,
                "page_start": 1,
                "page_end": 2,
                "section_title": "Introduction",
                "text": (
                    "Scientific research involves complex workflows including literature review, "
                    "hypothesis generation, experiment design, and result analysis. Recent "
                    "advances in large language models have enabled the development of AI agents "
                    "that can assist researchers at various stages. We propose a multi-agent "
                    "framework where specialized agents collaborate to support the research "
                    "lifecycle. Each agent is responsible for a specific task such as paper "
                    "summarization, citation recommendation, idea extraction, or cross-paper "
                    "synthesis, and they communicate through a shared state representation."
                ),
            },
            {
                "chunk_index": 1,
                "page_start": 2,
                "page_end": 4,
                "section_title": "Agent Architecture",
                "text": (
                    "Our multi-agent system uses a supervisor-orchestrated architecture. A "
                    "supervisor agent routes tasks to specialized agents based on the task type. "
                    "The summarization agent generates structured summaries of research papers. "
                    "The citation recommendation agent retrieves relevant papers and suggests "
                    "citations based on draft text. The idea extraction agent identifies "
                    "potential research directions from paper content. A reflection agent "
                    "provides quality assessment and feedback. The agents share a common state "
                    "object that tracks the research context and accumulated results."
                ),
            },
            {
                "chunk_index": 2,
                "page_start": 4,
                "page_end": 6,
                "section_title": "RAG Integration",
                "text": (
                    "The multi-agent framework integrates Retrieval-Augmented Generation to "
                    "ground agent responses in actual paper content. Each agent can query a "
                    "vector store of paper chunks to retrieve relevant passages. The citation "
                    "recommendation agent uses cross-paper retrieval to find connections between "
                    "different research works. The RAG pipeline includes an evidence gate that "
                    "prevents the system from generating answers without sufficient supporting "
                    "evidence, reducing hallucination. This is particularly important for "
                    "research assistants where factual accuracy is critical."
                ),
            },
            {
                "chunk_index": 3,
                "page_start": 6,
                "page_end": 8,
                "section_title": "MCP Integration",
                "text": (
                    "The system exposes its capabilities through the Model Context Protocol "
                    "(MCP), allowing external AI tools and IDEs to invoke research assistant "
                    "functions. MCP tools include paper search, summary retrieval, idea search, "
                    "citation recommendation, chunk search, and idea saving. The MCP server "
                    "uses stdio transport and can be integrated with AI coding assistants. "
                    "Security measures include input validation, rate limiting, and separation "
                    "of read-only and write operations. The save_research_idea tool is the only "
                    "write-capable tool in the MCP interface."
                ),
            },
            {
                "chunk_index": 4,
                "page_start": 8,
                "page_end": 10,
                "section_title": "Experiments and Discussion",
                "text": (
                    "We evaluate the multi-agent framework on research assistance tasks "
                    "including paper summarization quality, citation relevance, and idea "
                    "novelty. The framework demonstrates that combining RAG with multi-agent "
                    "coordination produces more grounded and useful outputs compared to single "
                    "agent approaches. The cross-paper retrieval capability enables discovering "
                    "connections between Transformer architectures, retrieval-augmented "
                    "generation, and multi-agent workflows that would be difficult for a "
                    "researcher to identify manually. Future work includes integrating real-time "
                    "arXiv feeds and supporting collaborative research workflows."
                ),
            },
        ],
    },
]

DEMO_IDEAS = [
    {
        "title": "Attention-Enhanced Retrieval for Scientific Literature",
        "summary": (
            "Apply multi-head attention mechanisms from Transformer architecture to improve "
            "the retrieval component of RAG systems, enabling better cross-paper semantic "
            "matching in scientific literature search."
        ),
        "research_question": (
            "Can multi-head attention improve dense passage retrieval accuracy for "
            "cross-domain scientific literature compared to standard DPR?"
        ),
        "method_hint": (
            "Replace the dual-encoder DPR with a cross-encoder using multi-head attention "
            "between query and passage, fine-tune on scientific paper pairs."
        ),
        "tags": '["transformer", "retrieval", "attention", "RAG"]',
        "confidence": 0.82,
        "paper_index": 0,
        "chunk_indices": [0, 1],
    },
    {
        "title": "RAG-Grounded Multi-Agent Research Assistant",
        "summary": (
            "Combine RAG with multi-agent coordination to build a research assistant that "
            "grounds its recommendations in retrieved paper content, reducing hallucination "
            "and improving citation accuracy."
        ),
        "research_question": (
            "How can RAG evidence gates be integrated into a multi-agent research workflow "
            "to ensure factual accuracy across summarization, citation, and idea extraction?"
        ),
        "method_hint": (
            "Implement a shared RAG pipeline accessible to all agents, with an evidence "
            "threshold that gates agent outputs. Evaluate on paper QA and citation tasks."
        ),
        "tags": '["RAG", "multi-agent", "evidence-gate", "research-assistant"]',
        "confidence": 0.78,
        "paper_index": 1,
        "chunk_indices": [0, 2],
    },
    {
        "title": "MCP-Based Collaborative Research Protocol",
        "summary": (
            "Design a Model Context Protocol extension for multi-agent research collaboration, "
            "enabling external AI tools to coordinate paper analysis and idea synthesis across "
            "research teams."
        ),
        "research_question": (
            "What MCP tool interface design best supports collaborative multi-agent research "
            "workflows while maintaining security and data integrity?"
        ),
        "method_hint": (
            "Extend the existing MCP server with collaborative tools for shared paper "
            "annotations and cross-session idea tracking. Evaluate with simulated multi-user "
            "research scenarios."
        ),
        "tags": '["MCP", "collaboration", "multi-agent", "protocol"]',
        "confidence": 0.75,
        "paper_index": 2,
        "chunk_indices": [0, 3],
    },
]


async def seed_demo():
    await init_db()

    embedder = get_embedding_provider()

    created_papers = 0
    skipped_papers = 0
    created_chunks = 0
    created_ideas = 0
    skipped_ideas = 0

    async with async_session() as session:
        paper_records: list[Paper] = []

        for paper_data in DEMO_PAPERS:
            existing = await session.execute(
                select(Paper).where(Paper.filename == paper_data["filename"])
            )
            existing_paper = existing.scalar_one_or_none()

            if existing_paper is not None:
                print(f"  SKIPPED paper: {paper_data['title']} (already exists)")
                skipped_papers += 1
                paper_records.append(existing_paper)
                continue

            paper = Paper(
                title=paper_data["title"],
                filename=paper_data["filename"],
                file_path=paper_data["file_path"],
                status="completed",
                created_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2025, 1, 15, 10, 5, 0, tzinfo=timezone.utc),
            )
            session.add(paper)
            await session.flush()

            chunk_texts = [c["text"] for c in paper_data["chunks"]]
            embeddings = await embedder.embed_texts(chunk_texts)

            for i, chunk_data in enumerate(paper_data["chunks"]):
                chunk = PaperChunk(
                    paper_id=paper.id,
                    chunk_index=chunk_data["chunk_index"],
                    text=chunk_data["text"],
                    page_start=chunk_data["page_start"],
                    page_end=chunk_data["page_end"],
                    section_title=chunk_data["section_title"],
                    embedding=embeddings[i],
                )
                session.add(chunk)
                created_chunks += 1

            print(f"  CREATED paper: {paper_data['title']} ({len(paper_data['chunks'])} chunks)")
            created_papers += 1
            paper_records.append(paper)

        await session.flush()

        for idea_data in DEMO_IDEAS:
            existing_idea = await session.execute(
                select(Idea).where(Idea.title == idea_data["title"])
            )
            if existing_idea.scalar_one_or_none() is not None:
                print(f"  SKIPPED idea: {idea_data['title']} (already exists)")
                skipped_ideas += 1
                continue

            paper = paper_records[idea_data["paper_index"]]

            chunks_result = await session.execute(
                select(PaperChunk)
                .where(PaperChunk.paper_id == paper.id)
                .order_by(PaperChunk.chunk_index)
            )
            paper_chunks = list(chunks_result.scalars().all())

            idea = Idea(
                paper_id=paper.id,
                title=idea_data["title"],
                summary=idea_data["summary"],
                research_question=idea_data["research_question"],
                method_hint=idea_data["method_hint"],
                tags=idea_data["tags"],
                confidence=idea_data["confidence"],
                status="saved",
                created_at=datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
            )
            session.add(idea)
            await session.flush()

            for ci in idea_data["chunk_indices"]:
                if ci < len(paper_chunks):
                    chunk = paper_chunks[ci]
                    idea_source = IdeaSource(
                        idea_id=idea.id,
                        paper_id=paper.id,
                        chunk_id=chunk.id,
                        chunk_index=chunk.chunk_index,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        text_excerpt=chunk.text[:200],
                    )
                    session.add(idea_source)

            print(f"  CREATED idea: {idea_data['title']}")
            created_ideas += 1

        await session.commit()

    print()
    print("=" * 60)
    print("Seed Demo Summary")
    print("=" * 60)
    print(f"  Papers:  {created_papers} created, {skipped_papers} skipped")
    print(f"  Chunks:  {created_chunks} created")
    print(f"  Ideas:   {created_ideas} created, {skipped_ideas} skipped")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed_demo())
