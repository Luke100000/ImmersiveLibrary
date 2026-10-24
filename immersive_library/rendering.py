import asyncio
import os

from playwright.async_api import (
    Browser,
    Page,
    Playwright,
    ViewportSize,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)

from immersive_library.models import Content

RENDER_CONCURRENCY_LIMIT = max(1, int(os.getenv("RENDER_CONCURRENCY_LIMIT", "2")))


class BrowserRenderer:
    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._browser_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(RENDER_CONCURRENCY_LIMIT)
        self._pages: list[Page] = []

    async def _get_browser(self) -> Browser:
        async with self._browser_lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()

            if self._browser is None or not self._browser.is_connected():
                self._browser = await self._playwright.chromium.launch(
                    args=[
                        "--use-gl=swiftshader",
                        "--enable-webgl",
                        "--ignore-gpu-blocklist",
                        "--disable-dev-shm-usage",
                    ]
                )

            return self._browser

    async def _new_page(self, browser: Browser, url: str) -> Page:
        context = await browser.new_context(device_scale_factor=1)
        try:
            page = await context.new_page()
            response = await page.goto(url, wait_until="domcontentloaded")
            if response is not None and not response.ok:
                raise RuntimeError(f"Render page returned HTTP {response.status}")

            await page.wait_for_function("typeof window.renderPreview === 'function'")
            return page
        except BaseException:
            await context.close()
            raise

    async def close(self) -> None:
        try:
            if self._browser is not None:
                await self._browser.close()
        finally:
            self._browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None

    async def render_png(
        self,
        url: str,
        project: str,
        content: Content,
        width: int,
        height: int,
        timeout_ms: int = 15000,
    ) -> bytes:
        try:
            return await self._render_once(
                url, project, content, width, height, timeout_ms
            )
        except PlaywrightError as exc:
            if "Render context was lost" not in str(exc):
                raise

        return await self._render_once(url, project, content, width, height, timeout_ms)

    async def _render_once(
        self,
        url: str,
        project: str,
        content: Content,
        width: int,
        height: int,
        timeout_ms: int,
    ) -> bytes:
        async with self._semaphore, asyncio.timeout(timeout_ms / 1000):
            browser = await self._get_browser()
            page = self._pages.pop() if self._pages else None
            if page is not None and (
                page.is_closed() or page.context.browser != browser or page.url != url
            ):
                await page.context.close()
                page = None

            if page is None:
                page = await self._new_page(browser, url)

            try:
                await page.set_viewport_size(ViewportSize(width=width, height=height))
                await page.evaluate(
                    "(options) => window.renderPreview(options)",
                    {
                        "project": project,
                        "content": content.model_dump(mode="json"),
                        "width": width,
                        "height": height,
                    },
                )
                png = await page.locator("#render-container").screenshot(
                    type="png",
                    omit_background=True,
                )
            except BaseException:
                await page.context.close()
                raise

            self._pages.append(page)
            return png
