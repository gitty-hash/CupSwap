"""Bonus: a small MCP server that exposes CupSwap's match-status tool over stdio.

Run standalone:  python -m cupswap.mcp_server
The buyer agent connects to it (when "Use MCP for check_match_status" is on), discovers the
tool schema with list_tools, and calls it with call_tool, so the integration is protocol-based
instead of a hard-wired Python import (Chapter 5: MCP clients / protocol / servers).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from cupswap import domain  # noqa: E402

server = MCPServer("cupswap-match-status")


@server.tool()
def check_match_status(match_id: str) -> str:
    """Return the live status of a World Cup 2026 match on CupSwap: teams, venue, kickoff,
    days to kickoff, whether it is postponed or completed, and whether it is a marquee matchup."""
    return json.dumps(domain.match_status(match_id))


if __name__ == "__main__":
    server.run("stdio")
