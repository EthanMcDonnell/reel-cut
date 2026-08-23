"""Shared Playwright stealth helpers to reduce bot-detection."""

import time

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
    "Checking your browser...",
    "X-Hashcash-Solution",
)


def is_bot_block(html: str) -> bool:
    """True if `html` is an anti-bot interstitial rather than the requested page."""
    if len(html) > 50000:  # real articles are big; interstitials are tiny
        return False
    return any(marker in html for marker in _BLOCK_MARKERS)


# Whether a request gets walled is decided per request, not per source: the same URL and
# the same stealth profile can sail through one attempt and get challenged on the next.
# A DataDome/Cloudflare interstitial never resolves on its own (polled one for 15s, the
# HTML never changed), so only a fresh context gets another roll of the dice. Proof-of-work
# walls are the exception and clear themselves — see wait_out_challenge, which runs first.
BOT_BLOCK_RETRIES = 3


async def wait_out_challenge(page, timeout_ms: int = 20000) -> bool:
    """Give a self-resolving anti-bot interstitial time to clear. True if the page is through.

    Hashcash proof-of-work walls ("Checking your browser...") solve in the page and reload
    themselves, typically in 3-5s. Without this wait the caller screenshots the challenge or
    reads an empty body, and every snippet then misses with a misleading "text not found"
    rather than a block. Returns immediately when the page was never walled, so the cost on
    an unblocked page is one content() read.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    walled = False
    while True:
        try:
            if not is_bot_block(await page.content()):
                if walled:
                    # The challenge clears by reloading, so the replacement document can still
                    # be in flight here — long enough for document.body to read as null and
                    # crash whatever JS the caller runs next. Settle before handing it back.
                    try:
                        await page.wait_for_load_state("load", timeout=10000)
                        await page.wait_for_function("() => !!document.body", timeout=10000)
                    except Exception:
                        pass
                return True
        except Exception:
            pass  # content() throws mid-reload, which is exactly what we are waiting for
        walled = True
        if time.monotonic() >= deadline:
            return False
        await page.wait_for_timeout(500)


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
