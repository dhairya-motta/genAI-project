# 🤖 Website Automation Agent

An intelligent browser automation agent that uses **Groq Vision AI** (Llama 4 Scout) and **Playwright** to autonomously navigate web pages, identify elements, and perform tasks without manual intervention.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     agent.py (Main Loop)                 │
│                                                          │
│   ┌──────────┐    ┌────────────┐    ┌────────────────┐   │
│   │Screenshot│───▶│  Groq AI   │───▶│ Execute Actions│   │
│   │  (PNG)   │    │ (Analyze)  │    │ (Browser Tools)│   │
│   └──────────┘    └────────────┘    └────────────────┘   │
│        ▲                                    │            │
│        └────────────────────────────────────┘            │
│                   Loop until done                        │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                 browser_tools.py (Tools)                  │
│                                                          │
│   open_browser    │  navigate_to_url  │  take_screenshot │
│   click_on_screen │  send_keys        │  scroll          │
│   double_click    │  close            │                  │
└──────────────────────────────────────────────────────────┘
```

## How It Works

1. **Open Browser** → Launches Chromium via Playwright
2. **Navigate** → Goes to the user-specified URL
3. **Screenshot** → Captures the current page state
4. **AI Analysis** → Sends screenshot to Groq Vision, which identifies elements and returns coordinates + actions
5. **Execute** → Agent performs clicks, typing, key presses, scrolling based on AI response
6. **Repeat** → Loop continues until the task is done or max iterations reached

## Setup

### Prerequisites
- Python 3.10+
- A Groq API key ([Get one from Groq](https://console.groq.com/))

### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Configuration

Edit the `.env` file and add your Groq API key:

```
GROQ_API_KEY=gsk_your_actual_api_key_here
```

## Running the Agent

### Interactive mode (prompts for URL & task):
```bash
source venv/bin/activate
python agent.py
```

### Direct mode (pass URL & task as arguments):
```bash
python agent.py https://youtube.com "Search for Bohemian Rhapsody by Queen"
python agent.py https://ui.shadcn.com/docs/forms/react-hook-form "Fill the Username with JohnDoe and Bio with Hello World"
python agent.py https://google.com "Search for weather in New York"
```

## Project Structure

```
04/
├── agent.py           # Main agent logic & Groq integration
├── browser_tools.py   # Modular browser automation tools (Playwright)
├── .env               # API key configuration (not committed)
├── requirements.txt   # Python dependencies
├── screenshots/       # Auto-generated screenshots from each run
└── README.md          # This file
```

## Design Decisions

| Decision | Rationale |
|---|---|
| **Groq Vision** over DOM parsing | More intelligent — works like a human looking at the screen |
| **Generic task input** | Agent works on any website with any task, not hardcoded |
| **Action history tracking** | AI gets context of what it already did, preventing loops |
| **Screenshot-based loop** | Each iteration gets fresh visual state for better decisions |
| **Modular tools** | Each browser action is a separate function, easy to test/extend |
| **Coordinate-based clicking** | Matches the assignment requirement for `click_on_screen(x, y)` |
| **Max iteration limit** | Safety mechanism to prevent infinite loops |

## Error Handling

- **Browser not open** → `RuntimeError` with clear message
- **Navigation timeout** → 30-second timeout with Playwright error
- **Groq parse failure** → Graceful fallback, continues to next iteration
- **Browser closed manually** → Agent handles it gracefully without crashing
- **Max iterations** → Agent stops after 15 iterations to prevent runaway loops
