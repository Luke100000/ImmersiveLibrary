import asyncio
import os
from urllib.parse import urlparse

from playwright.async_api import ViewportSize, async_playwright

RENDER_CONCURRENCY_LIMIT = max(1, int(os.getenv("RENDER_CONCURRENCY_LIMIT", "2")))
render_semaphore = asyncio.Semaphore(RENDER_CONCURRENCY_LIMIT)


async def render_headless_png(
    url: str,
    width: int,
    height: int,
    timeout_ms: int = 15000,
) -> bytes:
    async with render_semaphore:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                args=[
                    "--use-gl=swiftshader",
                    "--enable-webgl",
                    "--ignore-gpu-blocklist",
                    "--disable-dev-shm-usage",
                ]
            )

            page = await browser.new_page(
                viewport=ViewportSize(width=width, height=height),
                device_scale_factor=1,
            )
            allowed = urlparse(url)

            async def restrict_network(route):
                target = urlparse(route.request.url)
                same_origin = (
                    target.scheme == allowed.scheme
                    and target.hostname == allowed.hostname
                    and target.port == allowed.port
                )
                if same_origin or target.scheme in {"data", "blob"}:
                    await route.continue_()
                else:
                    await route.abort()

            await page.route("**/*", restrict_network)
            try:
                await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                await page.wait_for_function(
                    """
                    () => {
                        const container = document.getElementById("render-container");
                        if (!container) return false;
                        const ready = container.renderReady;
                        return ready === "1" || ready === "error";
                    }
                    """,
                    timeout=timeout_ms,
                )
                container = await page.query_selector("#render-container")
                if container is not None:
                    return await container.screenshot(
                        type="png",
                        omit_background=True,
                    )
                return await page.screenshot(
                    type="png",
                    full_page=False,
                    omit_background=True,
                )
            finally:
                await browser.close()
