from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.database import engine, check_db_connection
from app.config import settings


async def smoke_check():
    results = []

    print("=" * 60)
    print("Research Paper Assistant - Smoke Check")
    print("=" * 60)

    print(f"\nVersion: {settings.APP_VERSION}")
    print("Database target: configured")

    print("\n--- 1. Backend Health ---")
    db_ok = await check_db_connection()
    status = "PASS" if db_ok else "FAIL"
    results.append(db_ok)
    print(f"  Database connection: {status}")

    print("\n--- 2. pgvector Extension ---")
    vector_ok = False
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname='vector'")
            )
            row = result.fetchone()
            if row is not None:
                vector_ok = True
                print(f"  pgvector version: {row[0]}  PASS")
            else:
                print("  pgvector extension not found  FAIL")
    except Exception:
        print("  pgvector check error  FAIL")
    results.append(vector_ok)

    print("\n--- 3. Core Tables ---")
    required_tables = ["papers", "paper_chunks", "ideas", "idea_sources", "agent_runs", "model_call_events"]
    tables_ok = True
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
            )
            existing = {row[0] for row in result.fetchall()}
            for table in required_tables:
                if table in existing:
                    print(f"  {table}: exists  PASS")
                else:
                    print(f"  {table}: missing  FAIL")
                    tables_ok = False
    except Exception:
        print("  Table check error  FAIL")
        tables_ok = False
    results.append(tables_ok)

    print("\n--- 4. MCP Tool Import ---")
    mcp_ok = False
    try:
        from app.mcp.tools import (
            tool_search_papers,
            tool_get_paper_summary,
            tool_search_ideas,
            tool_recommend_citations,
            tool_search_paper_chunks,
            tool_save_research_idea,
        )
        mcp_ok = True
        print("  All 6 MCP tools imported successfully  PASS")
    except ImportError as e:
        print(f"  MCP tool import failed: {e}  FAIL")
    results.append(mcp_ok)

    print("\n" + "=" * 60)
    all_pass = all(results)
    if all_pass:
        print("RESULT: ALL CHECKS PASSED")
    else:
        print("RESULT: SOME CHECKS FAILED")
    print("=" * 60)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(smoke_check()))
