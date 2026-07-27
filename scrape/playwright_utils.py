"""Shared Playwright stealth helpers to reduce bot-detection."""

STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--ignore-gpu-blocklist",
    "--enable-webgl",
    "--enable-accelerated-2d-canvas",
    "--use-gl=swiftshader",
]

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# Markers of an anti-bot interstitial (DataDome, Cloudflare, Akamai) served instead of
# the real page. These pages parse fine and extract to empty text, so without an explicit
# check a hard block looks identical to "article had no content".
_BLOCK_MARKERS = (
    "captcha-delivery.com",
    "/cdn-cgi/challenge-platform",
    "Just a moment...",
    "Attention Required! | Cloudflare",
    "Access Denied",
    "Pardon Our Interruption",
)


def is_bot_block(html: str) -> bool:
    """True if `html` is an anti-bot interstitial rather than the requested page."""
    if len(html) > 50000:  # real articles are big; interstitials are tiny
        return False
    return any(marker in html for marker in _BLOCK_MARKERS)


async def stealth_context(browser, device_scale_factor: float = 1):
    return await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=device_scale_factor,
        user_agent=_USER_AGENT,
        locale="en-US",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
