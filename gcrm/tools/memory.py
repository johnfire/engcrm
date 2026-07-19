"""
Open Brain memory wrapper.

Provides two functions used by agents and the supervisor:
  capture_thought(content) — write an observation or learning to Open Brain
  search_gcrm_thoughts(query) — semantic search over gcrm-tagged thoughts

Both are no-ops when OPEN_BRAIN_URL / OPEN_BRAIN_TOKEN are not configured,
so tests and dev environments don't need the service available.
"""
import asyncio
import logging
import re

logger = logging.getLogger(__name__)

_METADATA_RE = re.compile(
    r"^(Captured:|Type:|Project:|Status:|Topics:|People:|Actions:|---)",
    re.MULTILINE,
)


def _get_config() -> tuple[str, str]:
    from gcrm.config import OPEN_BRAIN_TOKEN, OPEN_BRAIN_URL
    return OPEN_BRAIN_URL, OPEN_BRAIN_TOKEN


# Module-level references patched in tests
OPEN_BRAIN_URL: str = ""
OPEN_BRAIN_TOKEN: str = ""


def _load_config() -> None:
    global OPEN_BRAIN_URL, OPEN_BRAIN_TOKEN
    url, token = _get_config()
    OPEN_BRAIN_URL = url
    OPEN_BRAIN_TOKEN = token


_load_config()


def _run_tool(tool_name: str, arguments: dict) -> str:
    """Call an Open Brain MCP tool synchronously. Returns empty string on failure."""
    if not OPEN_BRAIN_URL or not OPEN_BRAIN_TOKEN:
        return ""

    async def _inner() -> str:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        headers = {"x-brain-key": OPEN_BRAIN_TOKEN}
        async with streamablehttp_client(OPEN_BRAIN_URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                texts = [block.text for block in result.content if hasattr(block, "text")]
                return "\n".join(texts)

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lambda: asyncio.run(_inner()))
                return future.result(timeout=10)
        else:
            return asyncio.run(_inner())
    except Exception as error:
        logger.warning("memory: %s failed: %s", tool_name, error)
        return ""


def capture_thought(content: str, project: str = "gcrm") -> None:
    """Write an observation or learning to Open Brain."""
    _run_tool("capture_thought", {"content": content, "project": project})


def search_gcrm_thoughts(query: str, limit: int = 5) -> list[str]:
    """
    Semantic search over gcrm thoughts in Open Brain.
    Returns a list of content strings (metadata stripped), up to `limit`.
    Returns [] when unconfigured or on error.
    """
    raw = _run_tool("search_thoughts", {"query": f"gcrm {query}", "limit": limit, "threshold": 0.45})
    if not raw:
        return []

    results = []
    for block in re.split(r"--- Result \d+.*---", raw):
        lines = [
            line.strip() for line in block.splitlines()
            if line.strip() and not _METADATA_RE.match(line.strip())
            and not line.strip().startswith("Found ")
        ]
        content = " ".join(lines).strip()
        if content:
            results.append(content)

    return results[:limit]
