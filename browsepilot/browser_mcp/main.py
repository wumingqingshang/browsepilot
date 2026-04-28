"""browser-mcp entry point — load config, register tools, start server."""

import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

from browser_mcp.tools import set_allowed_domains

domains = os.getenv("ALLOWED_DOMAINS", "")
if domains:
    set_allowed_domains([d.strip() for d in domains.split(",")])

# Import tool modules to trigger @mcp.tool() decorator registration
import browser_mcp.tools.navigate           # noqa: F401
import browser_mcp.tools.click              # noqa: F401
import browser_mcp.tools.type_text          # noqa: F401
import browser_mcp.tools.get_content        # noqa: F401
import browser_mcp.tools.screenshot         # noqa: F401
import browser_mcp.tools.scroll             # noqa: F401
import browser_mcp.tools.execute_script     # noqa: F401
import browser_mcp.tools.get_page_structure # noqa: F401

from browser_mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="sse")
