from __future__ import annotations

import pytest

from implementations.crawl_challenge import (
    CHALLENGE_AWS_WAF,
    CHALLENGE_AWS_WAF_CAPTCHA,
    CHALLENGE_CLOUDFLARE,
    CHALLENGE_MAX_CHARS,
    UNSOLVABLE_CHALLENGES,
    challenge_kind,
    challenge_tokens,
)

# The page AWS WAF served for every content.php page of one Acalog catalog,
# trimmed to the parts the detector reads.
AWS_WAF_PAGE = """<!DOCTYPE html><html lang="en"><head><title></title>
<script type="text/javascript">
window.awsWafCookieDomainList = [];
window.gokuProps = {"key":"AQID","iv":"CgAE","context":"Mbf2"};
</script>
<script src="https://dee3a4cb0537.749fc3d2.us-east-1.token.awswaf.com/dee3a4cb0537/fe844be64334/0d78bee904c0/challenge.js"></script>
</head><body><div id="challenge-container"></div>
<script type="text/javascript">
AwsWafIntegration.saveReferrer();
AwsWafIntegration.getToken().then(() => { window.location.reload(true); });
</script></body></html>"""

CLOUDFLARE_PAGE = (
    "<html><head><title>Just a moment...</title></head><body>"
    "<script>window._cf_chl_opt={cvId:'3'};</script></body></html>"
)

COURSE_PAGE = "<html><body><h1>ENGL 101</h1><p>3 credits</p></body></html>"


def test_the_waf_header_names_the_challenge_whatever_the_body_says() -> None:
    headers = {"X-Amzn-Waf-Action": "challenge"}
    assert challenge_kind(202, headers, "") == CHALLENGE_AWS_WAF
    assert challenge_kind(202, headers, COURSE_PAGE) == CHALLENGE_AWS_WAF


def test_the_waf_captcha_header_is_its_own_kind() -> None:
    headers = {"x-amzn-waf-action": "captcha"}
    assert challenge_kind(405, headers, "") == CHALLENGE_AWS_WAF_CAPTCHA
    assert CHALLENGE_AWS_WAF_CAPTCHA in UNSOLVABLE_CHALLENGES
    assert CHALLENGE_AWS_WAF not in UNSOLVABLE_CHALLENGES


def test_cloudflare_says_so_in_a_header() -> None:
    headers = {"cf-mitigated": "challenge"}
    assert challenge_kind(403, headers, "") == CHALLENGE_CLOUDFLARE


def test_a_saved_waf_page_is_recognised_from_its_markers_alone() -> None:
    assert challenge_kind(202, {}, AWS_WAF_PAGE) == CHALLENGE_AWS_WAF
    assert challenge_kind(None, None, AWS_WAF_PAGE) == CHALLENGE_AWS_WAF


def test_a_cloudflare_interstitial_is_recognised_from_its_markers() -> None:
    assert challenge_kind(200, {}, CLOUDFLARE_PAGE) == CHALLENGE_CLOUDFLARE


@pytest.mark.parametrize(
    "html",
    [
        COURSE_PAGE,
        "",
        # One marker is a mention, not an interstitial.
        "<p>Our site uses AwsWafIntegration to protect forms.</p>",
        # Cloudflare injects this into ordinary pages.
        '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
        "<h1>ENGL 101</h1>",
    ],
)
def test_a_real_page_is_not_a_challenge(html: str) -> None:
    assert challenge_kind(200, {"content-type": "text/html"}, html) is None


def test_a_large_page_is_never_read_for_markers() -> None:
    padding = "x" * CHALLENGE_MAX_CHARS
    assert challenge_kind(200, {}, AWS_WAF_PAGE + padding) is None


def test_only_challenge_token_cookies_are_kept() -> None:
    cookies = [
        {"name": "aws-waf-token", "value": "abc"},
        {"name": "cf_clearance", "value": "def"},
        {"name": "PHPSESSID", "value": "ghi"},
        {"name": "AWSALB", "value": "jkl"},
    ]
    assert challenge_tokens(cookies) == {
        "aws-waf-token": "abc",
        "cf_clearance": "def",
    }
    assert challenge_tokens([]) == {}
