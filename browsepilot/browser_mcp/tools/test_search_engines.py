"""Tests for search engine selector configuration."""

from browser_mcp.tools.search_engines import (
    SEARCH_ENGINES, match_search_engine,
)


class TestMatchSearchEngine:
    def test_match_bing_exact(self):
        assert match_search_engine("https://www.bing.com") == "bing.com"

    def test_match_bing_search_page(self):
        assert match_search_engine("https://www.bing.com/search?q=test") == "bing.com"

    def test_match_baidu(self):
        assert match_search_engine("https://www.baidu.com") == "baidu.com"

    def test_match_google(self):
        assert match_search_engine("https://www.google.com") == "google.com"

    def test_match_google_www_subdomain(self):
        assert match_search_engine("https://www.google.com/search?q=test") == "google.com"

    def test_no_match_unknown(self):
        assert match_search_engine("https://github.com") is None

    def test_no_match_empty(self):
        assert match_search_engine("") is None

    def test_no_match_none(self):
        assert match_search_engine(None) is None


class TestSearchEnginesConfig:
    def test_bing_has_selectors(self):
        bing = SEARCH_ENGINES["bing.com"]
        assert bing["input_selector"] == "#sb_form_q"
        assert bing["submit_selector"] == "#sb_form_go"
        assert bing["search_url"] == "https://www.bing.com"

    def test_baidu_has_selectors(self):
        baidu = SEARCH_ENGINES["baidu.com"]
        assert baidu["input_selector"] == "#kw"
        assert baidu["submit_selector"] == "#su"

    def test_google_has_selectors(self):
        google = SEARCH_ENGINES["google.com"]
        assert google["input_selector"] == "textarea[name='q']"
        assert "btnK" in google["submit_selector"]

    def test_all_engines_have_required_keys(self):
        for name, cfg in SEARCH_ENGINES.items():
            assert "search_url" in cfg, f"{name} missing search_url"
            assert "input_selector" in cfg, f"{name} missing input_selector"
            assert "submit_selector" in cfg, f"{name} missing submit_selector"
