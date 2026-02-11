from __future__ import annotations

from playwright.async_api import async_playwright


async def render_headless_png(
    url: str,
    width: int,
    height: int,
    timeout_ms: int = 15000,
) -> bytes:
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
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
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
