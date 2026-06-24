"""
browser_tools.py — Modular browser automation tools for the Website Automation Agent.

Tools provided:
    - open_browser        → Launch a Chromium browser instance
    - navigate_to_url     → Navigate to a given URL
    - take_screenshot     → Capture the current viewport as a PNG
    - click_on_screen(x, y) → Perform mouse click at coordinates
    - double_click        → Double-click at coordinates
    - send_keys           → Type text into the focused element
    - scroll              → Scroll the page up or down
    - fill_by_label       → Fill a form field by its visible label text (most reliable)
    - fill_field          → Fill a form field by CSS selector
"""

import os
import logging
from datetime import datetime
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, Page, Playwright

# ── Logger ──────────────────────────────────────────────────────────────────────
logger = logging.getLogger("browser_tools")

# ── Directory for screenshots ───────────────────────────────────────────────────
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


class BrowserSession:
    """Manages a single Playwright browser session."""

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    # ── Tool: open_browser ──────────────────────────────────────────────────────
    def open_browser(self, headless: bool = False) -> str:
        """
        Initialize and launch a Chromium browser instance.

        Args:
            headless: Run in headless mode (default False for demo/viva).

        Returns:
            Status message confirming the browser is open.
        """
        if self._browser and self._browser.is_connected():
            logger.info("Browser already open — reusing existing session.")
            return "Browser already open."

        logger.info("Launching Chromium (headless=%s) …", headless)
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=["--window-size=1280,800", "--disable-infobars"],
        )
        context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            no_viewport=False,
        )
        self._page = context.new_page()
        logger.info("Browser launched successfully.")
        return "Browser opened successfully."

    # ── Tool: navigate_to_url ───────────────────────────────────────────────────
    def navigate_to_url(self, url: str) -> str:
        """
        Navigate the browser to a URL and wait for the page to fully load.

        Args:
            url: The target URL.

        Returns:
            Status message with page title.
        """
        self._ensure_page()
        logger.info("Navigating to %s …", url)
        self._page.goto(url, wait_until="networkidle", timeout=30000)
        title = self._page.title()
        logger.info("Page loaded — title: '%s'", title)
        return f"Navigated to {url}. Page title: '{title}'"

    # ── Tool: take_screenshot ───────────────────────────────────────────────────
    def take_screenshot(self, label: str = "") -> str:
        """
        Capture the current viewport as a PNG file.

        Args:
            label: Optional label appended to the filename.

        Returns:
            Absolute path to the saved screenshot.
        """
        self._ensure_page()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{label}" if label else ""
        filename = f"screenshot_{timestamp}{suffix}.png"
        filepath = os.path.join(SCREENSHOT_DIR, filename)
        self._page.screenshot(path=filepath, full_page=False)
        logger.info("Screenshot saved → %s", filepath)
        return filepath

    # ── Tool: click_on_screen ───────────────────────────────────────────────────
    def click_on_screen(self, x: int, y: int) -> str:
        """
        Perform a mouse click at (x, y) pixel coordinates in the viewport.

        Args:
            x: Horizontal coordinate (0 to 1279).
            y: Vertical coordinate (0 to 799).

        Returns:
            Confirmation of the click.
        """
        self._ensure_page()
        logger.info("Clicking at (%d, %d) …", x, y)
        self._page.mouse.click(x, y)
        self._page.wait_for_timeout(500)
        logger.info("Click performed at (%d, %d).", x, y)
        return f"Clicked at ({x}, {y})."

    # ── Tool: double_click ──────────────────────────────────────────────────────
    def double_click(self, x: int, y: int) -> str:
        """
        Perform a double-click at (x, y) pixel coordinates.

        Args:
            x: Horizontal coordinate.
            y: Vertical coordinate.

        Returns:
            Confirmation of the double-click.
        """
        self._ensure_page()
        logger.info("Double-clicking at (%d, %d) …", x, y)
        self._page.mouse.dblclick(x, y)
        self._page.wait_for_timeout(500)
        logger.info("Double-click performed at (%d, %d).", x, y)
        return f"Double-clicked at ({x}, {y})."

    # ── Tool: send_keys ─────────────────────────────────────────────────────────
    def send_keys(self, text: str) -> str:
        """
        Type text into the currently focused element.

        Args:
            text: The string to type.

        Returns:
            Confirmation of the text input.
        """
        self._ensure_page()
        logger.info("Typing: '%s'", text)
        self._page.keyboard.type(text, delay=50)
        self._page.wait_for_timeout(300)
        logger.info("Text typed successfully.")
        return f"Typed: '{text}'"

    # ── Tool: scroll ────────────────────────────────────────────────────────────
    def scroll(self, direction: str = "down", amount: int = 300) -> str:
        """
        Scroll the page to reveal hidden elements.

        Args:
            direction: 'up' or 'down'.
            amount: Pixels to scroll.

        Returns:
            Confirmation of the scroll action.
        """
        self._ensure_page()
        delta = amount if direction == "down" else -amount
        logger.info("Scrolling %s by %d px …", direction, amount)
        self._page.mouse.wheel(0, delta)
        self._page.wait_for_timeout(600)
        logger.info("Scrolled %s by %d px.", direction, amount)
        return f"Scrolled {direction} by {amount}px."

    # ── Tool: fill_by_label ─────────────────────────────────────────────────────
    def fill_by_label(self, label_text: str, text: str) -> str:
        """
        Fill a form field by its visible label text.

        Strategy:
          1. Use get_by_label() but iterate ALL matches and skip buttons/links —
             only fill actual <input>, <textarea>, or [contenteditable] elements.
          2. Fall back to CSS attribute selectors (aria-label, placeholder, title,
             name) targeting only fillable tags.
          3. On any fillable match, click it to focus, then fill() — if fill()
             refuses (e.g. web-component), fall back to keyboard.type().

        Args:
            label_text: The visible label text (case-insensitive).
            text: The text to fill.

        Returns:
            'OK' on success, error string on failure.
        """
        self._ensure_page()
        logger.info("fill_by_label('%s', '%s') …", label_text, text)

        FILLABLE_TAGS = {"input", "textarea", "select"}

        def _do_fill(loc) -> bool:
            """Click loc to focus it, then fill or type. Returns True on success."""
            try:
                loc.scroll_into_view_if_needed(timeout=5000)
                loc.click(timeout=3000)
                try:
                    loc.fill(text, timeout=2000)
                except Exception:
                    # Custom web-components may reject .fill() — use keyboard
                    self._page.keyboard.press("Control+a")
                    self._page.keyboard.press("Delete")
                    self._page.keyboard.type(text, delay=40)
                self._page.wait_for_timeout(400)
                logger.info("fill_by_label('%s') filled successfully.", label_text)
                return True
            except Exception as ex:
                logger.debug("_do_fill failed: %s", ex)
                return False

        # ── Strategy 1: Playwright get_by_label — skip non-fillable elements ─────
        try:
            all_matches = self._page.get_by_label(label_text, exact=False).all()
            for loc in all_matches:
                try:
                    tag = loc.evaluate("el => el.tagName.toLowerCase()")
                    is_ce = loc.evaluate("el => el.isContentEditable")
                    if tag in FILLABLE_TAGS or is_ce:
                        if _do_fill(loc):
                            return "OK"
                except Exception:
                    continue
        except Exception as e:
            logger.debug("get_by_label failed: %s", e)

        # ── Strategy 2: CSS attribute selectors on fillable tags ──────────────────
        css_patterns = [
            f"input[aria-label*='{label_text}' i]",
            f"textarea[aria-label*='{label_text}' i]",
            f"input[placeholder*='{label_text}' i]",
            f"textarea[placeholder*='{label_text}' i]",
            f"input[title*='{label_text}' i]",
            f"textarea[title*='{label_text}' i]",
            f"input[name='{label_text.lower()}']",
            f"input[name*='{label_text.lower()}']",
        ]
        for css in css_patterns:
            try:
                loc = self._page.locator(css).first
                # count() is lazy — check if any exist
                loc.wait_for(state="attached", timeout=800)
                logger.info("fill_by_label: using CSS fallback '%s'", css)
                if _do_fill(loc):
                    return "OK"
            except Exception:
                continue

        logger.warning("fill_by_label: no fillable element found for '%s'", label_text)
        return f"FAILED: no fillable element found for label '{label_text}'"

    # ── Tool: fill_field ────────────────────────────────────────────────────────
    def fill_field(self, selector: str, text: str) -> str:
        """
        Fill a form field by CSS selector.

        Scrolls the matched element into view, clears it, then fills it.
        Use fill_by_label when a visible label exists — it's more reliable.

        Args:
            selector: CSS selector for the input/textarea.
            text: The text to fill.

        Returns:
            'OK' on success, error message on failure.
        """
        self._ensure_page()
        logger.info("Filling selector '%s' with '%s' …", selector, text)
        try:
            locator = self._page.locator(selector).first
            locator.scroll_into_view_if_needed(timeout=5000)
            locator.click(timeout=3000)
            try:
                locator.fill(text, timeout=2000)
            except Exception as e:
                logger.debug("Locator.fill failed, falling back to keyboard type: %s", e)
                self._page.keyboard.press("Control+a")
                self._page.keyboard.type(text, delay=50)
            self._page.wait_for_timeout(400)
            logger.info("Selector '%s' filled successfully.", selector)
            return "OK"
        except Exception as e:
            logger.warning("fill_field failed for '%s': %s", selector, e)
            return f"FAILED: {e}"

    # ── Helper: page reference ──────────────────────────────────────────────────
    @property
    def page(self) -> Page:
        """Return the active Playwright page object."""
        self._ensure_page()
        return self._page

    # ── Cleanup ─────────────────────────────────────────────────────────────────
    def close(self):
        """Gracefully close the browser and Playwright, ignoring errors."""
        try:
            if self._browser:
                logger.info("Closing browser …")
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._page = None
        self._playwright = None
        logger.info("Browser session closed.")

    # ── Internal ────────────────────────────────────────────────────────────────
    def _ensure_page(self):
        if not self._page:
            raise RuntimeError("Browser not open. Call open_browser() first.")
