"""
agent.py — AI-driven Website Automation Agent powered by Groq Vision.

A generic browser automation agent that performs any task on any website.
It uses a vision-based loop: screenshot → AI analysis → browser action → repeat.

Usage:
    python agent.py                                      # Interactive mode
    python agent.py <url> "<task>"                       # Direct mode

Examples:
    python agent.py https://youtube.com "Search for Bohemian Rhapsody by Queen"
    python agent.py https://ui.shadcn.com/docs/forms/react-hook-form "Fill Username with JohnDoe and Bio with Hello World"
"""

import os
import sys
import json
import base64
import logging
import time
from openai import OpenAI
from browser_tools import BrowserSession

# ── Viewport constants (must match BrowserSession launch args) ──────────────────
VP_WIDTH = 1280
VP_HEIGHT = 800

# ── Logging Setup ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-14s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent")


# ── Load API Key ────────────────────────────────────────────────────────────────
def load_api_key() -> str:
    """Load Groq API key from .env file or GROQ_API_KEY environment variable."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GROQ_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    if key and key != "your_groq_api_key_here":
                        return key

    key = os.environ.get("GROQ_API_KEY", "")
    if key:
        return key

    logger.error("No GROQ_API_KEY found. Set it in .env or as an environment variable.")
    sys.exit(1)


def encode_image(image_path: str) -> str:
    """Read an image file and return base64-encoded string."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def clamp(x: int, y: int) -> tuple[int, int]:
    """
    Clamp (x, y) coordinates to the visible viewport.
    The AI sometimes hallucinates out-of-bounds coordinates.
    """
    cx = max(0, min(x, VP_WIDTH - 1))
    cy = max(0, min(y, VP_HEIGHT - 1))
    if cx != x or cy != y:
        logger.warning("Coordinate clamped (%d,%d) → (%d,%d) — was out of %dx%d viewport",
                       x, y, cx, cy, VP_WIDTH, VP_HEIGHT)
    return cx, cy


# ── Groq Vision: Analyze Screenshot ─────────────────────────────────────────────
def ask_groq(client: OpenAI, screenshot_path: str, task: str, history: list[str]) -> dict:
    """
    Send the current screenshot to Groq Vision and get a list of browser
    actions to execute to progress toward the user's task.

    Args:
        client: OpenAI-compatible client pointed at Groq.
        screenshot_path: Path to the viewport screenshot PNG.
        task: The user's task description.
        history: List of previously executed action summaries.

    Returns:
        Dict with 'observations', 'task_progress', and 'actions' list.
    """
    logger.info("Sending screenshot to Groq …")

    history_text = ""
    if history:
        history_text = "\n\nACTIONS ALREADY DONE (do NOT repeat these):\n"
        for i, h in enumerate(history, 1):
            history_text += f"  {i}. {h}\n"

    prompt = f"""You are an intelligent browser automation agent. Look at this screenshot 
and decide what actions to perform NEXT to complete the user's task.

USER'S TASK: {task}
{history_text}

VIEWPORT: exactly {VP_WIDTH}×{VP_HEIGHT} px. Coordinates must be within this range.

=== ACTION PRIORITY (use in this order) ===

1. fill_by_label  ← USE THIS FIRST for any labeled form input or textarea.
   Finds the field by the text of its <label>. Very reliable, works even
   if the field is not visible — it auto-scrolls to it.
   Example: {{"action":"fill_by_label","label":"Username","text":"JohnDoe","reason":"..."}}
   Example: {{"action":"fill_by_label","label":"Bio","text":"Hello World","reason":"..."}}

2. fill  ← Use ONLY when you have a SPECIFIC CSS selector with attributes.
   NEVER use bare element names like 'textarea', 'input', 'div'.
   For form fields with visible labels, ALWAYS use fill_by_label instead.
   Example: {{"action":"fill","selector":"input[name='search_query']","text":"hello","reason":"..."}}

3. click  ← For buttons, links, checkboxes (not for text inputs — use fill_by_label).
   Coordinates MUST be inside the viewport (x: 0-{VP_WIDTH-1}, y: 0-{VP_HEIGHT-1}).
   If target is not visible, scroll first, then click.
   Example: {{"action":"click","x":640,"y":400,"reason":"..."}}

4. scroll  ← To reveal content or navigate. Use BEFORE clicking if unsure.
   Example: {{"action":"scroll","direction":"down","amount":400,"reason":"..."}}

5. key  ← Press keyboard keys (Enter, Tab, Escape, etc.)
   Example: {{"action":"key","key":"Enter","reason":"..."}}

6. type  ← Type into the currently focused element (after a click).
   Example: {{"action":"type","text":"hello","reason":"..."}}

7. done  ← ONLY when the task is fully complete.
   Example: {{"action":"done","reason":"Both fields filled successfully"}}

=== RULES ===
- Return at most 3 actions per response (allows re-evaluation).
- For form fields, ALWAYS use fill_by_label or fill — NEVER click+type for inputs.
- If you see the form fields, fill them immediately with fill_by_label.
- Do NOT repeat actions already in the history.
- If the task is complete, return exactly one "done" action.

Respond ONLY with valid JSON — no markdown, no code fences:

{{
    "observations": "What you currently see on screen",
    "task_progress": "Summary of what has been accomplished",
    "actions": [ ... ]
}}"""

    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encode_image(screenshot_path)}",
                            "detail": "high",
                        },
                    },
                ],
            }],
            max_tokens=1024,
            temperature=0.1,
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if the model adds them
        if raw.startswith("```"):
            raw = "\n".join(
                line for line in raw.split("\n")
                if not line.strip().startswith("```")
            )

        logger.debug("Groq raw response: %s", raw)
        return json.loads(raw)

    except json.JSONDecodeError as e:
        logger.error("JSON parse error: %s | Raw: %s", e, raw[:300])
        return {"observations": "parse error", "task_progress": "", "actions": []}
    except Exception as e:
        logger.error("Groq API error: %s", e)
        return {"observations": "api error", "task_progress": "", "actions": []}


# ── Execute Actions ─────────────────────────────────────────────────────────────
def execute_actions(session: BrowserSession, actions: list, history: list[str]) -> bool:
    """
    Execute actions returned by Groq. Returns True when 'done' is reached.
    All executed actions are appended to history for AI context.
    """
    for action in actions:
        act = action.get("action", "")
        reason = action.get("reason", "")
        logger.info("▸ %-15s │ %s", act, reason)

        try:
            if act == "fill_by_label":
                label = action["label"]
                text = action["text"]
                result = session.fill_by_label(label, text)
                history.append(f"fill_by_label('{label}', '{text}') → {result}")

            elif act == "fill":
                selector = action["selector"]
                text = action["text"]
                # Reject dangerously generic selectors that match wrong elements
                bare = selector.strip().lower()
                if bare in {"textarea", "input", "div", "span", "form", "p", "button"}:
                    msg = f"Rejected bare selector '{selector}' — use fill_by_label with the label text instead"
                    logger.warning(msg)
                    history.append(f"REJECTED fill('{selector}') — too generic, use fill_by_label")
                    continue
                result = session.fill_field(selector, text)
                history.append(f"fill('{selector}', '{text}') → {result}")

            elif act == "click":
                x, y = clamp(int(action["x"]), int(action["y"]))
                session.click_on_screen(x, y)
                history.append(f"click({x},{y}) — {reason}")

            elif act == "double_click":
                x, y = clamp(int(action["x"]), int(action["y"]))
                session.double_click(x, y)
                history.append(f"double_click({x},{y}) — {reason}")

            elif act == "type":
                text = action["text"]
                session.send_keys(text)
                history.append(f"type('{text}') — {reason}")

            elif act == "key":
                key = action["key"]
                session.page.keyboard.press(key)
                session.page.wait_for_timeout(300)
                history.append(f"key('{key}') — {reason}")

            elif act == "scroll":
                direction = action.get("direction", "down")
                amount = int(action.get("amount", 300))
                session.scroll(direction, amount)
                history.append(f"scroll({direction},{amount}px) — {reason}")

            elif act == "done":
                logger.info("✓ Task complete: %s", reason)
                history.append(f"DONE — {reason}")
                return True

            else:
                logger.warning("Unknown action: %s", act)

        except Exception as e:
            logger.error("Action '%s' failed: %s", act, e)
            history.append(f"FAILED {act}: {e}")

    return False


# ── Main Agent Loop ─────────────────────────────────────────────────────────────
def run_agent():
    """
    Entry point:
      1. Parse URL and task from args or prompt interactively.
      2. Open browser, navigate to URL.
      3. Loop: screenshot → Groq analysis → execute actions → repeat.
      4. Stop on 'done' or after max_iterations.
    """
    # ── Get URL and task ────────────────────────────────────────────────────
    if len(sys.argv) >= 3:
        target_url = sys.argv[1]
        task = " ".join(sys.argv[2:])
    else:
        print("\n╔══════════════════════════════════════════════════╗")
        print("║     🤖  Website Automation Agent (Groq Vision)  ║")
        print("╚══════════════════════════════════════════════════╝\n")
        target_url = input("  Enter URL: ").strip()
        task = input("  Describe the task: ").strip()

    if not target_url.startswith("http"):
        target_url = "https://" + target_url

    logger.info("URL  : %s", target_url)
    logger.info("Task : %s", task)

    # ── Setup ───────────────────────────────────────────────────────────────
    client = OpenAI(api_key=load_api_key(), base_url="https://api.groq.com/openai/v1")
    session = BrowserSession()
    history: list[str] = []
    max_iterations = 25

    try:
        logger.info("=" * 60)
        logger.info("AGENT START")
        logger.info("=" * 60)

        # Step 1 — Open browser and navigate
        logger.info(session.open_browser(headless=False))
        logger.info(session.navigate_to_url(target_url))
        session.page.wait_for_timeout(2500)  # Let JS render

        # Step 2 — Agent loop
        for iteration in range(1, max_iterations + 1):
            logger.info("─" * 60)
            logger.info("Iteration %d / %d", iteration, max_iterations)
            logger.info("─" * 60)

            screenshot = session.take_screenshot(label=f"iter{iteration}")
            result = ask_groq(client, screenshot, task, history)

            logger.info("Observations : %s", result.get("observations", ""))
            logger.info("Progress     : %s", result.get("task_progress", ""))

            actions = result.get("actions", [])
            logger.info("Actions count: %d", len(actions))

            if not actions:
                logger.warning("No actions returned — retrying in 5 seconds.")
                time.sleep(5)
                continue

            done = execute_actions(session, actions, history)
            if done:
                break

            try:
                session.page.wait_for_timeout(800)
            except Exception:
                logger.warning("Browser was closed externally — stopping loop.")
                break

        # Step 3 — Final screenshot
        logger.info("=" * 60)
        logger.info("AGENT DONE — Final screenshot")
        logger.info("=" * 60)
        logger.info(session.take_screenshot(label="final"))

        logger.info("─" * 60)
        logger.info("FULL ACTION HISTORY:")
        for i, h in enumerate(history, 1):
            logger.info("  %2d. %s", i, h)
        logger.info("─" * 60)

        logger.info("Task complete. Closing browser in 5 seconds …")
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            pass

    except Exception as e:
        logger.error("Agent error: %s", e, exc_info=True)
    finally:
        session.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    run_agent()
