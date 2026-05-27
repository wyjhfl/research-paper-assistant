import asyncio
import logging

from app.database import init_db
from app.mcp.server import mcp

logging.basicConfig(level=logging.INFO)


async def main():
    await init_db()
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
