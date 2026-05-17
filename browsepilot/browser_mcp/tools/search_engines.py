"""Known CSS selectors for common search engines.

These are stable, verified selectors that bypass the LLM's need to
guess or discover selectors via get_page_structure.
"""

from urllib.parse import urlparse

SEARCH_ENGINES = {
    "bing.com": {
        "search_url": "https://www.bing.com",
        "input_selector": "#sb_form_q",
        "submit_selector": "#sb_form_go",
    },
    "baidu.com": {
        "search_url": "https://www.baidu.com",
        "input_selector": "#kw",
        "submit_selector": "#su",
    },
    "google.com": {
        "search_url": "https://www.google.com",
        "input_selector": "textarea[name='q']",
        "submit_selector": "input[name='btnK']",
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
        if hostname == engine_name or hostname.endswith("." + engine_name):
            return engine_name
    return None
