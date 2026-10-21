"""Turn outputs/insights.json into two markdown reports.

- outputs/weekly_pulse.md  : weekly product pulse, worded by an LLM (Groq)
- outputs/fee_explainer.md : fixed text explaining the charges on Groww trades

The LLM only writes the wording for the top themes, the key observation and
the action ideas. The user quotes are inserted from insights.json verbatim.
Without an API key (or if the call fails) template text is used instead.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

try:
    from groq import Groq
except ImportError:  # groq is optional: without it we fall back to templates
    Groq = None

BASE_DIR = Path(__file__).resolve().parent
INSIGHTS_PATH = BASE_DIR / "outputs" / "insights.json"
PULSE_PATH = BASE_DIR / "outputs" / "weekly_pulse.md"
EXPLAINER_PATH = BASE_DIR / "outputs" / "fee_explainer.md"

DEFAULT_MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0.3
MAX_WORDS = 250
MAX_COMPLETION_TOKENS = 900
REASONING_EFFORT = "low"
# The LLM only writes the wording for the sections; the quotes and the rest of
# the file are added from insights.json. Keeping the sections short keeps the
# whole file under MAX_WORDS.
LLM_INSTRUCTION = (
    "Use only these numbers. Do not invent facts. Write at most 150 words in total. "
    "Return 3 sections: TOP THEMES, KEY OBSERVATION, ACTION IDEAS (exactly 3 numbered). "
    "Keep TOP THEMES to one short line per theme, KEY OBSERVATION to 2 short sentences and "
    "each ACTION IDEA to one short sentence."
)

FEE_BULLETS = [
    "Brokerage: ₹20 or 0.1% per executed order, whichever is lower, with a minimum of ₹5. "
    "It applies to each executed order, so a buy and a sell are charged separately.",
    "DP charge: applied per sell transaction of delivery shares — ₹3.5 depository charge "
    "(₹3.25 for female account holders) plus ₹16.5 Groww charge (₹0 if the debit value is under "
    "₹100), plus GST.",
    "Statutory charges (set by the government, exchanges and SEBI, not by Groww): STT 0.1% on "
    "delivery buy and sell, 0.025% on intraday sell; stamp duty 0.015% on delivery buy, 0.003% on "
    "intraday buy; NSE exchange transaction charge 0.00297%; SEBI turnover charge 0.0001%; NSE "
    "investor protection fund charge 0.0001%.",
    "GST: 18% GST is applied on brokerage, DP charges, exchange transaction charges, SEBI turnover "
    "charges and investor protection fund charges.",
    "Auto square-off: open intraday positions squared off by the system are charged ₹50 per "
    "position, plus GST.",
    "Where to check: Groww's brokerage calculator estimates the total charges for a trade, and the "
    "contract note lists the final charges actually deducted.",
]

SOURCE_LINKS = [
    "https://groww.in/pricing",
    "https://groww.in/calculators/brokerage-calculator",
]

LAST_CHECKED = "2026-10-21"

TEMPLATE_ACTIONS = {
    "Customer support & withdrawals": "Cut first-response time on withdrawal and support "
    "tickets, and show a visible escalation path in the app.",
    "Charges & brokerage": "Show a pre-trade charge breakdown so every charge on top of "
    "brokerage is visible before the order is placed.",
    "App glitches & order issues": "Instrument order-placement failures and make stop loss "
    "execution reliable in the order ticket.",
}

TEMPLATE_COMMENTS = {
    "rising": "rising this week",
    "falling": "easing off this week",
    "stable": "steady week over week",
}


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def load_insights(path: Path = INSIGHTS_PATH) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# --------------------------------------------------------------------------
# llm helpers
# --------------------------------------------------------------------------


def llm_payload(insights: dict) -> dict:
    """Only the data from insights.json that the model is allowed to see."""
    themes = [
        {
            "name": theme.get("name"),
            "review_count": theme.get("review_count"),
            "negative_count": theme.get("negative_count"),
            "this_week": theme.get("this_week"),
            "weekly_avg_before": theme.get("weekly_avg_before"),
            "trend": theme.get("trend"),
        }
        for theme in insights.get("themes", [])
    ]
    fee = insights.get("fee_issue", {})
    quotes = [
        {
            "theme": quote.get("theme"),
            "rating": quote.get("rating"),
            "thumbs_up": quote.get("thumbs_up"),
            "short_quote": quote.get("short_quote"),
        }
        for quote in insights.get("quotes", [])
    ]
    return {
        "total_reviews": insights.get("total_reviews"),
        "date_range": insights.get("date_range"),
        "top_themes": insights.get("top_themes"),
        "themes": themes,
        "fee_issue": {
            "name": fee.get("name"),
            "count": fee.get("count"),
            "counts": fee.get("counts"),
        },
        "quotes": quotes,
    }


def build_prompt(payload: dict, extra: str = "") -> str:
    prompt = (
        LLM_INSTRUCTION
        + "\n\nData:\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + "\n\nFormat:\n"
        "TOP THEMES\n"
        "- one bullet per theme in the given top_themes order, written as "
        "- <theme name>: <one short comment>\n"
        "KEY OBSERVATION\n"
        "2-3 sentences on what is going wrong and what is trending, naming the fee issue and its count\n"
        "ACTION IDEAS\n"
        "1. <idea for the first top theme>\n"
        "2. <idea for the second top theme>\n"
        "3. <idea for the third top theme>\n"
        "Do not write review quotes and do not use quotation marks: the quotes are added separately."
    )
    if extra:
        prompt += "\n\n" + extra
    return prompt


def call_llm(payload: dict, extra: str = "") -> str | None:
    """Call Groq. Returns None when there is no key, no SDK or the call fails."""
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    print(
        f"Using GROQ_MODEL={model} "
        f"(max_completion_tokens={MAX_COMPLETION_TOKENS}, reasoning_effort={REASONING_EFFORT})"
    )
    if not api_key:
        print("No GROQ_API_KEY found")
        return None
    if Groq is None:
        print("groq package is not installed")
        return None

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=TEMPERATURE,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            reasoning_effort=REASONING_EFFORT,
            messages=[{"role": "user", "content": build_prompt(payload, extra)}],
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            print("LLM returned empty content")
            return None
        return content
    except Exception as exc:  # noqa: BLE001 - never leak the key, only the type and message
        print(f"LLM call failed ({type(exc).__name__}): {exc}")
        return None


def parse_sections(text: str) -> dict[str, str]:
    """Split the model answer into TOP THEMES / KEY OBSERVATION / ACTION IDEAS."""
    pattern = re.compile(
        r"^\s*#*\s*(?:\*\*)?(TOP THEMES|KEY OBSERVATION|ACTION IDEAS)(?:\*\*)?\s*:?\s*(.*)$",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        head = match.group(2).strip().strip("*").strip()
        if head.startswith("(") and head.endswith(")"):
            head = ""  # the model echoing the instruction, not content
        body = text[match.end() : end].strip()
        sections[match.group(1).upper()] = (head + "\n" + body).strip() if head else body
    return sections


def bullet_lines(block: str) -> list[str]:
    """Bullet or numbered lines of a section, without the marker."""
    lines = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^([-*+]|\d+[.)])\s+", line):
            lines.append(re.sub(r"^([-*+]|\d+[.)])\s+", "", line).strip())
    return lines


def comment_for(theme: str, lines: list[str], trends: dict[str, str]) -> str:
    """The model's comment for a theme, or a template one."""
    for line in lines:
        if theme.lower() in line.lower():
            comment = re.sub(re.escape(theme), "", line, flags=re.IGNORECASE)
            comment = comment.lstrip(" :-–—").strip()
            if comment:
                return comment
    return TEMPLATE_COMMENTS.get(trends.get(theme, "stable"), TEMPLATE_COMMENTS["stable"])


# --------------------------------------------------------------------------
# document building
# --------------------------------------------------------------------------


def stars(rating: int) -> str:
    filled = max(0, min(5, int(rating)))
    return "★" * filled + "☆" * (5 - filled)


def build_top_themes(insights: dict, sections: dict[str, str]) -> str:
    theme_map = {t.get("name"): t for t in insights.get("themes", [])}
    trends = {name: theme_map[name].get("trend", "stable") for name in theme_map}
    lines = bullet_lines(sections.get("TOP THEMES", ""))

    out = []
    for name in insights.get("top_themes", []):
        theme = theme_map.get(name, {})
        comment = comment_for(name, lines, trends)
        out.append(
            f"- **{name}** — {comment} ({theme.get('review_count', '?')} reviews, "
            f"{theme.get('negative_count', '?')} negative, {theme.get('trend', '?')})"
        )
    return "\n".join(out)


def build_observation(insights: dict, sections: dict[str, str]) -> str:
    fee = insights.get("fee_issue", {})
    fee_name = fee.get("name", "the fee issue")
    fee_count = fee.get("count", 0)

    observation = " ".join(sections.get("KEY OBSERVATION", "").split())
    if not observation:
        top = insights.get("top_themes", [])
        first = top[0] if top else "the top theme"
        observation = (
            f"{first} leads the negative reviews, and the other top themes follow. "
            f"The fee issue to fix first is {fee_name}, mentioned in {fee_count} reviews."
        )
    if fee_name.lower() not in observation.lower() or str(fee_count) not in observation:
        observation += (
            f" The fee issue to fix first is {fee_name}, mentioned in {fee_count} reviews."
        )
    return observation


def build_actions(insights: dict, sections: dict[str, str]) -> str:
    top = insights.get("top_themes", [])
    ideas = bullet_lines(sections.get("ACTION IDEAS", ""))

    out = []
    for index, theme in enumerate(top[:3]):
        idea = ideas[index] if index < len(ideas) else TEMPLATE_ACTIONS.get(
            theme, f"Pick one concrete fix for {theme.lower()} and ship it this sprint."
        )
        out.append(f"{index + 1}. {idea}")
    return "\n".join(out)


def build_quotes(insights: dict) -> str:
    out = []
    for quote in insights.get("quotes", []):
        out.append(
            f"- {stars(quote.get('rating', 0))} \"{quote.get('short_quote', '')}\" "
            f"— {quote.get('theme', '')}"
        )
    return "\n".join(out)


def build_pulse(insights: dict, sections: dict[str, str], today: date | None = None) -> str:
    today = today or date.today()
    date_range = insights.get("date_range", {})
    span = f"{date_range.get('start', '?')} to {date_range.get('end', '?')}"

    return "\n".join(
        [
            f"# Groww Weekly Product Pulse — {today.isoformat()}",
            "",
            "## Top themes",
            "",
            build_top_themes(insights, sections),
            "",
            "## What users say",
            "",
            build_quotes(insights),
            "",
            "## Key observation",
            "",
            build_observation(insights, sections),
            "",
            "## Action ideas",
            "",
            build_actions(insights, sections),
            "",
            f"Source: {insights.get('total_reviews', '?')} Google Play reviews, {span}.",
        ]
    )


def build_fee_explainer() -> str:
    lines = [
        "# Charges on Groww stock trades beyond brokerage",
        "",
        "Why this exists: many users say they see 'hidden' charges on top of brokerage. "
        "These are the charges applied to a stock trade.",
        "",
    ]
    lines += [f"- {bullet}" for bullet in FEE_BULLETS]
    lines += ["", "Sources:"]
    for index, link in enumerate(SOURCE_LINKS, start=1):
        lines += [f"{index}. {link}"]
    lines += ["", f"Last checked: {LAST_CHECKED}", ""]
    return "\n".join(lines)


def word_count(text: str) -> int:
    return len(text.split())


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def make_outputs(insights: dict) -> dict:
    """Build both markdown documents from the insights dict."""
    payload = llm_payload(insights)
    llm_text = call_llm(payload)
    llm_used = bool(llm_text)
    sections = parse_sections(llm_text) if llm_text else {}

    pulse = build_pulse(insights, sections)
    count = word_count(pulse)

    if count > MAX_WORDS and llm_used:
        print(f"weekly_pulse.md is {count} words - asking the model to shorten it")
        shorter = call_llm(
            payload,
            extra=(
                "The previous draft was too long. Rewrite it much shorter, at most 100 words, "
                "keeping the same three sections and the same format."
            ),
        )
        if shorter:
            sections = parse_sections(shorter)
            pulse = build_pulse(insights, sections)
            count = word_count(pulse)
        else:
            print("Shorten call failed - falling back to template text")

    if count > MAX_WORDS:
        if llm_used:
            print(
                f"weekly_pulse.md is still {count} words (limit {MAX_WORDS}) after the shorten "
                "attempt - falling back to template text"
            )
        else:
            print(
                f"weekly_pulse.md is {count} words (limit {MAX_WORDS}) and no LLM text is "
                "available - using template text"
            )
        sections = {}
        llm_used = False
        pulse = build_pulse(insights, sections)
        count = word_count(pulse)

    if count > MAX_WORDS:
        # The template itself is over the limit: warn, but still write both files.
        print(
            f"WARNING: weekly_pulse.md is {count} words, over the {MAX_WORDS} word limit "
            "even with template text"
        )

    return {
        "weekly_pulse": pulse,
        "fee_explainer": build_fee_explainer(),
        "bullets": list(FEE_BULLETS),
        "source_links": list(SOURCE_LINKS),
        "llm_used": llm_used,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv(BASE_DIR / ".env")
    insights = load_insights()
    outputs = make_outputs(insights)

    PULSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PULSE_PATH.write_text(outputs["weekly_pulse"], encoding="utf-8")
    EXPLAINER_PATH.write_text(outputs["fee_explainer"], encoding="utf-8")

    print(f"Wrote {PULSE_PATH} ({word_count(outputs['weekly_pulse'])} words)")
    print(f"Wrote {EXPLAINER_PATH}")
    if outputs["llm_used"]:
        print(f"LLM used: {os.getenv('GROQ_MODEL', DEFAULT_MODEL)}")
    else:
        print("LLM not used — template fallback")


if __name__ == "__main__":
    main()
