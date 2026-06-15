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


async def stealth_context(browser, device_scale_factor: float = 1):
    return await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=device_scale_factor,
        user_agent=_USER_AGENT,
        locale="en-US",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
