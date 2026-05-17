"""Unit tests for security validators."""

import pytest
import browser_mcp.tools as tools_module
from browser_mcp.tools import validate_url, filter_js_script, set_allowed_domains


@pytest.fixture(autouse=True)
def reset_allowed_domains():
    """Reset ALLOWED_DOMAINS before and after each test."""
    set_allowed_domains([])
    yield
    set_allowed_domains([])


class TestValidateUrl:
    """Tests for validate_url function."""

    def test_allows_http_url(self):
        """validate_url should allow standard http URLs."""
        is_valid, msg = validate_url("http://example.com")
        assert is_valid is True
        assert msg == ""

    def test_allows_https_url(self):
        """validate_url should allow standard https URLs."""
        is_valid, msg = validate_url("https://example.com/path?q=1")
        assert is_valid is True
        assert msg == ""

    def test_allows_url_with_port(self):
        """validate_url should allow URLs with explicit ports."""
        is_valid, msg = validate_url("http://localhost:8080/page")
        assert is_valid is True

    def test_allows_url_with_subdomain(self):
        """validate_url should allow URLs with subdomains."""
        is_valid, msg = validate_url("https://sub.example.com/path")
        assert is_valid is True

    def test_blocks_file_protocol(self):
        """validate_url should block file:// URLs."""
        is_valid, msg = validate_url("file:///etc/passwd")
        assert is_valid is False
        assert "protocol_blocked" in msg
        assert "file://" in msg

    def test_blocks_file_protocol_no_double_slash(self):
        """validate_url should block file: URLs without //."""
        is_valid, msg = validate_url("file:C:/windows/system32")
        assert is_valid is False
        assert "protocol_blocked" in msg

    def test_blocks_non_http_scheme(self):
        """validate_url should block non-http schemes like ftp or javascript."""
        is_valid, msg = validate_url("ftp://example.com/file")
        assert is_valid is False
        assert "protocol_blocked" in msg
        assert "ftp" in msg

    def test_blocks_javascript_scheme(self):
        """validate_url should block javascript: URLs."""
        is_valid, msg = validate_url("javascript:alert(1)")
        assert is_valid is False
        assert "protocol_blocked" in msg

    def test_blocks_empty_string(self):
        """validate_url should handle empty string gracefully."""
        is_valid, msg = validate_url("")
        assert is_valid is False
        assert "protocol_blocked" in msg


class TestValidateUrlWithWhitelist:
    """Tests for validate_url with domain whitelist active."""

    def setup_method(self):
        """Set allowed domains before each test."""
        set_allowed_domains(["github.com", "example.com"])

    def teardown_method(self):
        """Clear allowed domains after each test."""
        set_allowed_domains([])

    def test_allows_whitelisted_domain(self):
        """validate_url should allow domains in the whitelist."""
        is_valid, msg = validate_url("https://github.com/user/repo")
        assert is_valid is True

    def test_allows_subdomain_of_whitelisted(self):
        """validate_url should allow subdomains of whitelisted domains."""
        is_valid, msg = validate_url("https://api.github.com")
        assert is_valid is True

    def test_blocks_non_whitelisted_domain(self):
        """validate_url should block domains not in the whitelist."""
        is_valid, msg = validate_url("https://evil.com")
        assert is_valid is False
        assert "domain_not_allowed" in msg

    def test_blocks_url_without_hostname(self):
        """validate_url should block URLs whose hostname is not in the whitelist."""
        is_valid, msg = validate_url("https://google.com")
        assert is_valid is False
        assert "domain_not_allowed" in msg


class TestValidateUrlWithWildcards:
    """Tests for validate_url with fnmatch wildcard patterns."""

    def teardown_method(self):
        set_allowed_domains([])

    def test_wildcard_star_dot_com_matches_any_com(self):
        """*.com should match any .com domain."""
        set_allowed_domains(["*.com"])
        assert validate_url("https://github.com")[0] is True
        assert validate_url("https://baidu.com")[0] is True
        assert validate_url("https://sub.example.com")[0] is True
        set_allowed_domains([])

    def test_wildcard_star_dot_com_blocks_org(self):
        """*.com should NOT match .org domains."""
        set_allowed_domains(["*.com"])
        is_valid, msg = validate_url("https://python.org")
        assert is_valid is False
        assert "domain_not_allowed" in msg
        set_allowed_domains([])

    def test_wildcard_star_dot_github_dot_star_matches_subdomain(self):
        """*.github.* matches subdomain.github.com and subdomain.github.io."""
        set_allowed_domains(["*.github.*"])
        assert validate_url("https://api.github.com")[0] is True
        assert validate_url("https://sub.github.io")[0] is True
        set_allowed_domains([])

    def test_wildcard_star_dot_github_dot_star_exact_requires_prefix(self):
        """*.github.* does NOT match github.com (no text before first dot)."""
        set_allowed_domains(["*.github.*"])
        is_valid, msg = validate_url("https://github.com")
        assert is_valid is False
        assert "domain_not_allowed" in msg
        set_allowed_domains([])

    def test_wildcard_question_mark(self):
        """? wildcard should match a single character."""
        set_allowed_domains(["???-test.com"])
        assert validate_url("https://abc-test.com")[0] is True
        assert validate_url("https://ab-test.com")[0] is False
        set_allowed_domains([])


class TestFilterJsScript:
    """Tests for filter_js_script function."""

    def test_allows_safe_script(self):
        """filter_js_script should allow safe JavaScript."""
        is_safe, msg = filter_js_script("document.title")
        assert is_safe is True
        assert msg == ""

    def test_allows_console_log(self):
        """filter_js_script should allow simple console.log."""
        is_safe, msg = filter_js_script("console.log('hello')")
        assert is_safe is True

    def test_allows_dom_manipulation(self):
        """filter_js_script should allow DOM manipulation."""
        is_safe, msg = filter_js_script(
            "document.querySelector('.btn').click()"
        )
        assert is_safe is True

    def test_allows_empty_script(self):
        """filter_js_script should allow empty string."""
        is_safe, msg = filter_js_script("")
        assert is_safe is True

    def test_blocks_eval(self):
        """filter_js_script should block eval."""
        is_safe, msg = filter_js_script("eval('alert(1)')")
        assert is_safe is False
        assert "eval" in msg

    def test_blocks_fetch(self):
        """filter_js_script should block fetch."""
        is_safe, msg = filter_js_script("fetch('https://evil.com')")
        assert is_safe is False
        assert "fetch" in msg

    def test_blocks_xml_http_request(self):
        """filter_js_script should block XMLHttpRequest."""
        is_safe, msg = filter_js_script("new XMLHttpRequest()")
        assert is_safe is False
        assert "XMLHttpRequest" in msg

    def test_blocks_websocket(self):
        """filter_js_script should block WebSocket."""
        is_safe, msg = filter_js_script("new WebSocket('ws://evil.com')")
        assert is_safe is False
        assert "WebSocket" in msg

    def test_blocks_localstorage(self):
        """filter_js_script should block localStorage access."""
        is_safe, msg = filter_js_script("localStorage.getItem('token')")
        assert is_safe is False
        assert "localStorage" in msg

    def test_blocks_sessionstorage(self):
        """filter_js_script should block sessionStorage access."""
        is_safe, msg = filter_js_script("sessionStorage.setItem('k', 'v')")
        assert is_safe is False
        assert "sessionStorage" in msg

    def test_allows_evaluate_not_a_keyword(self):
        """filter_js_script should allow 'evaluate' (word boundary working)."""
        is_safe, msg = filter_js_script("document.evaluate('//div', document)")
        assert is_safe is True
        assert msg == ""

    def test_blocks_eval_uppercase(self):
        """filter_js_script should block 'EVAL' (case insensitive)."""
        is_safe, msg = filter_js_script("EVAL('alert(1)')")
        assert is_safe is False
        assert "eval" in msg.lower()

    def test_blocks_non_string_input_int(self):
        """filter_js_script should return error for non-string input (int)."""
        is_safe, msg = filter_js_script(42)
        assert is_safe is False
        assert "invalid_input" in msg

    def test_blocks_non_string_input_none(self):
        """filter_js_script should return error for non-string input (None)."""
        is_safe, msg = filter_js_script(None)
        assert is_safe is False
        assert "invalid_input" in msg


class TestAllowedDomainsManagement:
    """Tests for set_allowed_domains function."""

    def test_sets_global_allowed_domains(self):
        """set_allowed_domains should set the global ALLOWED_DOMAINS."""
        set_allowed_domains(["gitlab.com", "bitbucket.org"])
        assert tools_module.ALLOWED_DOMAINS == ["gitlab.com", "bitbucket.org"]
        set_allowed_domains([])  # cleanup

    def test_empty_list_clears_allowed_domains(self):
        """set_allowed_domains with empty list should clear allowed domains."""
        set_allowed_domains([])
        assert tools_module.ALLOWED_DOMAINS == []
