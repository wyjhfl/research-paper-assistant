from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import (
    tool_search_papers,
    tool_get_paper_summary,
    tool_search_ideas,
    tool_recommend_citations,
    tool_search_paper_chunks,
    tool_save_research_idea,
)

mcp = FastMCP("research-paper-assistant")


@mcp.tool()
async def search_papers(query: str, limit: int = 5, user_id: str = "default") -> dict:
    return await tool_search_papers(query, limit, user_id)


@mcp.tool()
async def get_paper_summary(paper_id: int, user_id: str = "default") -> dict:
    return await tool_get_paper_summary(paper_id, user_id)


@mcp.tool()
async def search_ideas(query: str, limit: int = 5, user_id: str = "default") -> dict:
    return await tool_search_ideas(query, limit, user_id)


@mcp.tool()
async def recommend_citations(
    draft_text: str,
    paper_id: int | None = None,
    paper_ids: list[int] | None = None,
    limit: int = 5,
    user_id: str = "default",
) -> dict:
    return await tool_recommend_citations(draft_text, paper_id, paper_ids, limit, user_id)


@mcp.tool()
async def search_paper_chunks(
    query: str,
    paper_ids: list[int] | None = None,
    limit: int = 10,
    user_id: str = "default",
) -> dict:
    return await tool_search_paper_chunks(query, paper_ids, limit, user_id)


@mcp.tool()
async def save_research_idea(
    title: str,
    summary: str,
    tags: list[str],
    source_paper_ids: list[int],
    user_id: str = "default",
) -> dict:
    return await tool_save_research_idea(title, summary, tags, source_paper_ids, user_id)
