"""Known CSS selectors for common search engines.

These are stable, verified selectors that bypass the LLM's need to
guess or discover selectors via get_page_structure.
"""

from urllib.parse import urlparse

from browser_mcp.tools import _match_hostname

SEARCH_ENGINES = {
    "bing.com": {
        "search_url": "https://www.bing.com",
        "search_url_template": "https://www.bing.com/search?q={query}",
        "input_selector": "#sb_form_q",
    },
    "baidu.com": {
        "search_url": "https://www.baidu.com",
        "search_url_template": "https://www.baidu.com/s?wd={query}",
        "input_selector": "#kw",
    },
    "google.com": {
        "search_url": "https://www.google.com",
        "search_url_template": "https://www.google.com/search?q={query}",
        "input_selector": "textarea[name='q']",
    },
}


def match_search_engine(url: str) -> str | None:
    """Return the engine name if URL matches a known search engine domain."""
    if not url:
        return None
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return None
    for engine_name in SEARCH_ENGINES:
        if _match_hostname(hostname, engine_name):
            return engine_name
    return None
