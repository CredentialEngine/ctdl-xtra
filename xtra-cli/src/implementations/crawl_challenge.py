"""Bot-challenge interstitials: pages a site serves instead of the page asked for.

A firewall in front of a catalog can answer the first request from a new
browser with a small page whose only job is to run a script, earn a token,
and reload. AWS WAF does this with HTTP 202, which is below 400, so before
this module the crawler saved 206 such pages from one Acalog catalog as if
they were course listings, and followed no links from any of them.

The browser strategy uses this to wait the challenge out. Every strategy's
results also pass through it before they are saved, so an interstitial is a
retryable failure and never a page in the run.
"""

from __future__ import annotations

from collections.abc import Mapping

CHALLENGE_AWS_WAF = "aws-waf"
CHALLENGE_AWS_WAF_CAPTCHA = "aws-waf-captcha"
CHALLENGE_CLOUDFLARE = "cloudflare"

# Kinds a headless browser cannot get past by waiting. A CAPTCHA needs a
# person, so retrying it only spends the run's budget.
UNSOLVABLE_CHALLENGES = frozenset({CHALLENGE_AWS_WAF_CAPTCHA})

# An interstitial is a couple of kilobytes. A real page that merely mentions
# one of the marker words is much larger, so markers are only read below this.
CHALLENGE_MAX_CHARS = 64_000

# kind -> (markers, how many must appear). Ordered: the CAPTCHA is tested
# before the plain challenge because both load from .awswaf.com.
CHALLENGE_MARKERS: tuple[tuple[str, tuple[str, ...], int], ...] = (
    (
        CHALLENGE_AWS_WAF_CAPTCHA,
        ("AwsWafCaptcha", "captcha-container", "captcha.js", ".awswaf.com/"),
        2,
    ),
    (
        CHALLENGE_AWS_WAF,
        (
            "gokuProps",
            "AwsWafIntegration",
            "challenge-container",
            ".awswaf.com/",
            "challenge.js",
        ),
        2,
    ),
    # "/cdn-cgi/challenge-platform/" alone is not a signal: Cloudflare puts
    # it into ordinary pages too. The interstitial carries these.
    (
        CHALLENGE_CLOUDFLARE,
        (
            "_cf_chl_opt",
            "<title>Just a moment...</title>",
            "cf_chl_",
            "cf-chl-",
        ),
        2,
    ),
)

# Cookies a solved challenge leaves in the browser context. A new value is
# the sign that the challenge script finished and the page can be asked for
# again.
CHALLENGE_TOKEN_COOKIES = ("aws-waf-token", "cf_clearance")


def challenge_kind(
    status: int | None,
    headers: Mapping[str, str] | None,
    html: str,
) -> str | None:
    """Name the interstitial this response is, or None for a real page.

    Headers are believed first because they are the firewall speaking for
    itself: AWS WAF sends x-amzn-waf-action, Cloudflare cf-mitigated. The
    markers are for responses whose headers were not kept, such as a saved
    page or a backend that does not report them.
    """
    lowered = {key.lower(): value for key, value in (headers or {}).items()}
    action = (lowered.get("x-amzn-waf-action") or "").strip().lower()
    if action == "captcha":
        return CHALLENGE_AWS_WAF_CAPTCHA
    if action == "challenge":
        return CHALLENGE_AWS_WAF
    if (lowered.get("cf-mitigated") or "").strip().lower() == "challenge":
        return CHALLENGE_CLOUDFLARE
    if not html or len(html) > CHALLENGE_MAX_CHARS:
        return None
    for kind, markers, needed in CHALLENGE_MARKERS:
        if sum(1 for marker in markers if marker in html) >= needed:
            return kind
    return None


def challenge_tokens(cookies: list[Mapping[str, object]]) -> dict[str, str]:
    """The challenge-token cookies among a context's cookies, by name."""
    tokens: dict[str, str] = {}
    for cookie in cookies:
        name = str(cookie.get("name") or "")
        if name.startswith(CHALLENGE_TOKEN_COOKIES):
            tokens[name] = str(cookie.get("value") or "")
    return tokens
