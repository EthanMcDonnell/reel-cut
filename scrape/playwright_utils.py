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


# Whether a request gets walled is decided per request, not per source: the same URL and
# the same stealth profile can sail through one attempt and get challenged on the next.
# The interstitial never resolves on its own (polled one for 15s, the HTML never changed),
# so waiting longer is useless and only a fresh context gets another roll of the dice.
BOT_BLOCK_RETRIES = 3


_CONTEXT_OPTS = dict(
    viewport={"width": 1920, "height": 1080},
    user_agent=_USER_AGENT,
    locale="en-US",
    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
)


async def stealth_context(browser, device_scale_factor: float = 1):
    return await browser.new_context(device_scale_factor=device_scale_factor, **_CONTEXT_OPTS)


async def stealth_persistent_context(pw, user_data_dir: str, device_scale_factor: float = 1):
    """Headed context backed by a persistent profile.

    Lets a human clear a CAPTCHA once; the resulting cookie survives into later runs so
    the same source usually fetches headless afterwards.
    """
    return await pw.chromium.launch_persistent_context(
        user_data_dir=user_data_dir, headless=False, args=STEALTH_ARGS,
        device_scale_factor=device_scale_factor, **_CONTEXT_OPTS
    )
