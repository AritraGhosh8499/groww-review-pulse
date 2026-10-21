"""Groww Review Pulse — one page, one story, one button.

    Read reviews -> find the biggest problems -> write two documents -> approve.

Everything on the page is reused from the pipeline that already exists:

  - analyze.run_analysis()           reads the Play Store reviews and finds the
                                     themes, the real quotes and the fee issue
  - generate.make_outputs()          writes the weekly update and the fee
                                     explanation
  - mcp_server.append_to_doc()       saves the week to the team notes document
  - mcp_server.create_email_draft()  saves an email draft (it is never sent)

The last two only ever run after a person clicks "Approve & share".

Run with:  streamlit run app.py
"""

from __future__ import annotations

import html as html_lib
import os
import re
import time
from datetime import date
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from analyze import INPUT_CSV, load_reviews, run_analysis
from generate import EXPLAINER_PATH, LAST_CHECKED, PULSE_PATH, make_outputs, stars
from mcp_server import append_to_doc, create_email_draft
from run_workflow import log_decision

try:  # the SDK is optional - without it the app falls back to template text
    from groq import Groq  # noqa: F401

    GROQ_AVAILABLE = True
except Exception:  # noqa: BLE001
    GROQ_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent
NOTES_PATH = BASE_DIR / "outputs" / "notes_doc.md"
EMAIL_PATH = BASE_DIR / "outputs" / "email_draft.md"

load_dotenv(BASE_DIR / ".env")

st.set_page_config(
    page_title="Groww Review Pulse",
    page_icon="📊",
    layout="wide",
)

# --------------------------------------------------------------------------
# small pieces of text the page repeats
# --------------------------------------------------------------------------

# The theme names the analysis produces, in words a customer would use.
PLAIN_THEME_NAMES = {
    "Charges & brokerage": "Charges & brokerage",
    "Customer support & withdrawals": "Support & withdrawals",
    "App glitches & order issues": "App glitches & order issues",
    "Charts & features": "Charts & features",
    "Easy to use (positive)": "Easy to use (positive)",
}
POSITIVE_THEME = "Easy to use (positive)"

HOW_IT_WORKS = [
    "Read the recent Play Store reviews",
    "Find the biggest problems users keep repeating",
    "Write a weekly update and a customer explanation",
    "You approve it, then it is saved and drafted",
]

SOURCE_LINKS = [
    ("Groww pricing (official charges)", "https://groww.in/pricing"),
    (
        "Brokerage calculator",
        "https://groww.in/calculators/brokerage-calculator",
    ),
    (
        "Regulatory information",
        "https://groww.in/regulatory-and-other-information",
    ),
    (
        "Groww on Google Play",
        "https://play.google.com/store/apps/details?id=com.nextbillion.groww",
    ),
]

# --------------------------------------------------------------------------
# styling
# --------------------------------------------------------------------------

CSS = """
<style>
  .stApp, [data-testid="stAppViewContainer"] {
    font-family: "Source Sans Pro", "Segoe UI", -apple-system, sans-serif;
  }

  /* ---------- header ---------- */
  .hero { padding: 2px 0 0 0; }
  .hero h1 {
    font-size: 2.4rem; font-weight: 800; color: #1B1F23;
    margin: 0 0 8px 0; letter-spacing: -0.02em;
  }
  .lede {
    color: #4B5563; font-size: 1.06rem; line-height: 1.6;
    max-width: 900px; margin: 0 0 4px 0;
  }

  /* ---------- the 4 step strip ---------- */
  .strip {
    display: flex; align-items: center; flex-wrap: wrap;
    gap: 8px; margin: 16px 0 6px 0;
  }
  .strip-item {
    background: #F4F7F6; border: 1px solid #E4EAE8; border-radius: 999px;
    padding: 6px 14px; font-size: .88rem; font-weight: 600; color: #2E3A36;
  }
  .strip-arrow { color: #00B386; font-weight: 800; font-size: 1rem; }

  /* ---------- section titles ---------- */
  .section-title {
    display: flex; align-items: center; gap: 10px;
    font-size: 1.3rem; font-weight: 800; color: #1B1F23;
    margin: 30px 0 10px 0; letter-spacing: -0.01em;
  }
  .section-title::before {
    content: ""; display: inline-block; width: 5px; height: 22px;
    background: #00B386; border-radius: 3px;
  }
  .section-note { color: #6B7280; font-size: .95rem; line-height: 1.55; }

  /* ---------- the short answer ---------- */
  .answer {
    background: #F2FBF8; border: 1px solid #B9E6D6; border-radius: 16px;
    padding: 18px 24px; margin: 6px 0 10px 0;
    box-shadow: 0 1px 2px rgba(16,24,40,.05), 0 10px 24px rgba(16,24,40,.05);
  }
  .answer-label {
    font-size: .72rem; text-transform: uppercase; letter-spacing: .09em;
    color: #0A7D5F; font-weight: 800; margin-bottom: 8px;
  }
  .answer-list { margin: 0; padding-left: 20px; }
  .answer-list li {
    font-size: 1.08rem; line-height: 1.65; color: #1B1F23; margin-bottom: 8px;
  }
  .answer-list li:last-child { margin-bottom: 0; }

  /* ---------- horizontal bar chart ---------- */
  .bars { margin: 6px 0 4px 0; }
  .bar-row { display: flex; align-items: center; gap: 12px; margin: 7px 0; }
  .bar-label { flex: 0 0 240px; font-size: .9rem; color: #1B1F23; }
  .bar-track {
    flex: 1 1 auto; background: #F1F4F3; border-radius: 7px;
    height: 22px; overflow: hidden;
  }
  .bar-fill { height: 100%; background: #C6D3CF; border-radius: 7px; }
  .bar-fill.top { background: #00B386; }
  .bar-value {
    flex: 0 0 54px; text-align: right; font-size: .88rem; font-weight: 700;
    color: #1B1F23;
  }

  /* ---------- review cards ---------- */
  .review {
    background: #FFFFFF; border: 1px solid #E4EAE8;
    border-left: 4px solid #00B386; border-radius: 12px;
    padding: 13px 16px; margin: 0 0 10px 0;
    box-shadow: 0 1px 2px rgba(16,24,40,.05);
  }
  .review-top {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    margin-bottom: 8px;
  }
  .review-topic {
    font-size: .73rem; font-weight: 700; color: #0A7D5F;
    background: #E8F7F2; border: 1px solid #B9E6D6;
    border-radius: 999px; padding: 2px 11px;
  }
  .review-stars { color: #E8A33D; font-size: .95rem; letter-spacing: 1px; }
  .review-rating { font-size: .76rem; color: #8A9490; font-weight: 600; }
  .review-text {
    font-style: italic; color: #1B1F23; font-size: .97rem; line-height: 1.6;
  }
  .review-meta { font-size: .78rem; color: #8A9490; margin-top: 9px; }
  .caption { color: #8A9490; font-size: .82rem; margin-top: 2px; }

  /* ---------- evidence quotes ---------- */
  .evidence {
    color: #8A9490; font-size: .86rem; font-style: italic;
    line-height: 1.55; margin: 4px 0 4px 12px;
    border-left: 2px solid #E4EAE8; padding-left: 12px;
  }

  /* ---------- checklist ---------- */
  .checklist { margin: 10px 0 12px 0; }
  .check {
    display: flex; align-items: flex-start; gap: 10px;
    font-size: 1rem; color: #1B1F23; line-height: 1.5; margin-bottom: 8px;
  }
  .check .box {
    flex: 0 0 auto; font-size: 1.05rem; line-height: 1.35; color: #00B386;
  }

  /* ---------- badges ---------- */
  .badge {
    display: inline-block; padding: 3px 12px; border-radius: 999px;
    font-size: .76rem; font-weight: 700;
    background: #E8F7F2; color: #0A7D5F; border: 1px solid #B9E6D6;
  }
  .badge.amber { background: #FFF4DC; color: #8A5B00; border-color: #F2D9A8; }

  /* ---------- email header ---------- */
  .email-head {
    background: #F7F9F9; border: 1px solid #E4EAE8; border-radius: 10px;
    padding: 11px 15px; margin-bottom: 12px 0;
  }
  .email-head div {
    font-size: .86rem; color: #5C6763; line-height: 1.6;
  }
  .email-head b { color: #1B1F23; }

  /* ---------- bordered boxes look like paper ---------- */
  [data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px; border: 1px solid #E4EAE8;
    background-color: #FFFFFF; padding: 6px 16px 12px 16px;
    box-shadow: 0 1px 2px rgba(16,24,40,.05), 0 10px 24px rgba(16,24,40,.05);
  }

  /* ---------- technical note ---------- */
  .tech { color: #98A29E; font-size: .76rem; line-height: 1.5; margin-top: 14px; }

  /* ---------- sidebar ---------- */
  .side-step { font-size: .88rem; color: #4B5563; line-height: 1.45; padding: 3px 0; }
  .side-num {
    display: inline-block; width: 20px; height: 20px; line-height: 20px;
    text-align: center; border-radius: 50%; background: #E8F7F2;
    color: #0A7D5F; font-size: .7rem; font-weight: 700; margin-right: 8px;
  }

  code {
    background: #F1F4F3; border-radius: 5px; padding: 1px 5px;
    color: #0A7D5F; font-size: .82rem;
  }
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def esc(value: object) -> str:
    """Escape a value so it is safe to drop into our HTML cards."""
    return html_lib.escape(str(value), quote=True)


def plain_theme(name: str) -> str:
    """The friendlier name for a topic."""
    return PLAIN_THEME_NAMES.get(name, name)


def badge(text: str, style: str = "") -> str:
    css = f" {style}" if style else ""
    return f'<span class="badge{css}">{esc(text)}</span>'


def section(title: str, note: str = "") -> None:
    """A section heading, with an optional sentence under it."""
    st.markdown(f'<div class="section-title">{esc(title)}</div>', unsafe_allow_html=True)
    if note:
        st.markdown(
            f'<div class="section-note">{esc(note)}</div>', unsafe_allow_html=True
        )


def short_answer_html(bullets: list[str]) -> str:
    """The big highlighted card with the three plain-English bullets."""
    items = "".join(f"<li>{esc(bullet)}</li>" for bullet in bullets)
    return (
        '<div class="answer">'
        '<div class="answer-label">The short answer</div>'
        f'<ul class="answer-list">{items}</ul>'
        "</div>"
    )


def bar_chart_html(rows: list[tuple[str, int, bool]]) -> str:
    """A horizontal bar chart, top problems in Groww green and the rest grey."""
    biggest = max((value for _, value, _ in rows), default=0) or 1
    parts = ['<div class="bars">']
    for label, value, is_top in rows:
        width = max(1.5, round(100 * value / biggest, 1))
        parts.append(
            '<div class="bar-row">'
            f'<div class="bar-label">{esc(label)}</div>'
            '<div class="bar-track">'
            f'<div class="bar-fill{" top" if is_top else ""}" style="width:{width}%"></div>'
            "</div>"
            f'<div class="bar-value">{value}</div>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def review_card_html(quote: dict) -> str:
    """One real review, copied word-for-word."""
    rating = int(quote.get("rating", 0) or 0)
    return (
        '<div class="review">'
        '<div class="review-top">'
        f'<span class="review-topic">{esc(plain_theme(quote.get("theme", "")))}</span>'
        f'<span class="review-stars">{stars(rating)}</span>'
        f'<span class="review-rating">{rating} out of 5</span>'
        "</div>"
        f'<div class="review-text">“{esc(quote.get("short_quote", ""))}”</div>'
        f'<div class="review-meta">Posted on {esc(quote.get("date", ""))}</div>'
        "</div>"
    )


def evidence_html(text: str) -> str:
    """A small grey quote used as evidence."""
    return f'<div class="evidence">“{esc(text)}”</div>'


def email_body(pulse: str, explainer: str) -> str:
    """The same body the weekly workflow puts in the email draft."""
    return "\n".join(
        [
            pulse,
            "",
            "----- Reusable support snippet (copy/paste) -----",
            "",
            explainer,
        ]
    )


def latest_notes_entry() -> str:
    """The most recent entry of the team notes document, without the
    machine-readable block that is saved next to it."""
    if not NOTES_PATH.exists():
        return ""
    text = NOTES_PATH.read_text(encoding="utf-8")
    marker = "## Entry —"
    parts = text.split(marker)
    entry = text if len(parts) <= 1 else marker + parts[-1]
    return entry.split("### Payload")[0].strip()


def split_email(text: str) -> tuple[dict[str, str], str]:
    """Split the saved draft into its To/Subject/Status headers and the body."""
    headers: dict[str, str] = {}
    body: list[str] = []
    for line in text.splitlines():
        if not body and re.match(r"^(To|Subject|Status):\s", line):
            key, _, value = line.partition(":")
            headers[key.strip()] = value.strip()
        else:
            body.append(line)
    return headers, "\n".join(body).strip()


def ai_is_on() -> bool:
    """True when the weekly update can be worded by the AI model."""
    outputs = st.session_state.get("pulse_outputs")
    if outputs:
        return bool(outputs.get("llm_used"))
    return bool(os.getenv("GROQ_API_KEY")) and GROQ_AVAILABLE


# --------------------------------------------------------------------------
# the one big action
# --------------------------------------------------------------------------


def run_the_analysis() -> None:
    """Read the reviews, analyse them and write the two documents."""
    started = time.time()

    with st.status("Working on it…", expanded=True) as status:
        # 1 — read the reviews
        step = st.empty()
        step.markdown("⏳ Reading the recent reviews…")
        try:
            reviews = load_reviews(INPUT_CSV)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            status.update(label=f"Could not read the reviews: {exc}", state="error")
            return
        total = len(reviews)
        negative = sum(1 for review in reviews if review.get("rating") in (1, 2))
        time.sleep(0.3)
        step.markdown(f"✓ Reading {total:,} recent reviews…")

        # 2 — group them into topics
        step = st.empty()
        step.markdown("⏳ Grouping them into topics…")
        try:
            insights = run_analysis()
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            status.update(label=f"Could not read the reviews: {exc}", state="error")
            return
        time.sleep(0.3)
        step.markdown(f"✓ Grouping them into {len(insights.get('themes', []))} topics…")

        # 3 — the three biggest problems
        step = st.empty()
        step.markdown("⏳ Finding the 3 biggest problems…")
        top_themes = list(insights.get("top_themes", []))[:3]
        time.sleep(0.3)
        step.markdown("✓ Finding the 3 biggest problems…")

        # 4 — the charge users do not understand
        step = st.empty()
        step.markdown("⏳ Spotting the most confusing charge…")
        fee = insights.get("fee_issue", {}) or {}
        time.sleep(0.3)
        step.markdown("✓ Spotting the most confusing charge…")

        # 5 — write the weekly update with the AI
        step = st.empty()
        step.markdown("⏳ Writing the weekly update with AI…")
        try:
            outputs = make_outputs(insights)
        except Exception as exc:  # noqa: BLE001
            status.update(label=f"Could not write the update: {exc}", state="error")
            return
        time.sleep(0.3)
        step.markdown("✓ Writing the weekly update with AI…")

        # 6 — prepare the customer explanation and save both files
        step = st.empty()
        step.markdown("⏳ Preparing the customer explanation…")
        PULSE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PULSE_PATH.write_text(outputs["weekly_pulse"], encoding="utf-8")
        EXPLAINER_PATH.write_text(outputs["fee_explainer"], encoding="utf-8")
        time.sleep(0.3)
        step.markdown("✓ Preparing the customer explanation…")

        seconds = max(1, round(time.time() - started))

        st.session_state["pulse_insights"] = insights
        st.session_state["pulse_outputs"] = outputs
        st.session_state["pulse_summary"] = {
            "total": total,
            "negative": negative,
            "negative_pct": round(100 * negative / total) if total else 0,
            "fee": fee,
        }
        st.session_state["pulse_seconds"] = seconds

        status.update(
            label=f"✓ Done in {seconds} seconds", state="complete", expanded=False
        )


def clear_everything() -> None:
    """Forget the results so the page starts again from the top."""
    for key in (
        "pulse_insights",
        "pulse_outputs",
        "pulse_summary",
        "pulse_approval",
        "pulse_seconds",
    ):
        st.session_state.pop(key, None)


# --------------------------------------------------------------------------
# session state
# --------------------------------------------------------------------------

today = date.today().isoformat()
subject = f"Weekly Product Pulse + Customer Clarification — {today}"

# --------------------------------------------------------------------------
# sidebar
# --------------------------------------------------------------------------

with st.sidebar:
    st.markdown("#### How this works")
    for index, text in enumerate(HOW_IT_WORKS, start=1):
        st.markdown(
            f'<div class="side-step"><span class="side-num">{index}</span>{esc(text)}</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    st.markdown("#### AI status")
    if ai_is_on():
        st.markdown(badge("🟢 AI is on"), unsafe_allow_html=True)
        st.caption("The weekly update is worded by the AI model.")
    else:
        st.markdown(badge("🟡 AI is off — using a standard template", "amber"), unsafe_allow_html=True)
        st.caption("The weekly update uses the built-in wording instead.")

    st.divider()

    st.markdown("#### Sources")
    for label, link in SOURCE_LINKS:
        st.markdown(f"- [{label}]({link})")

    st.divider()
    st.caption("Nothing is saved to the team notes or the email draft until you approve.")

# --------------------------------------------------------------------------
# 0) header
# --------------------------------------------------------------------------

st.markdown(
    '<div class="hero">'
    "<h1>📊 Groww Review Pulse</h1>"
    '<div class="lede">We read what Groww users are saying on the Play Store and turn '
    "it into (1) a weekly update for the product team and (2) a ready-to-send "
    "explanation for customers confused about charges.</div>"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="strip">'
    '<span class="strip-item">📥 Read reviews</span>'
    '<span class="strip-arrow">→</span>'
    '<span class="strip-item">🔍 Find the biggest problems</span>'
    '<span class="strip-arrow">→</span>'
    '<span class="strip-item">✍️ Write the update</span>'
    '<span class="strip-arrow">→</span>'
    "<span class=\"strip-item\">✅ You approve before it’s shared</span>"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# 1) the one big button
# --------------------------------------------------------------------------

auto_run = bool(st.session_state.pop("pulse_auto_run", False))
clicked_run = st.button(
    "▶ Run this week’s analysis",
    type="primary",
    width="stretch",
)

ran_now = False
if clicked_run or auto_run:
    run_the_analysis()
    ran_now = True

insights = st.session_state.get("pulse_insights")
outputs = st.session_state.get("pulse_outputs")
summary = st.session_state.get("pulse_summary") or {}

if not outputs or not insights:
    st.markdown(
        '<div class="section-note">Takes about 20 seconds. Nothing is shared until '
        "you approve.</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# --------------------------------------------------------------------------
# 2) the short answer
# --------------------------------------------------------------------------

seconds = st.session_state.get("pulse_seconds")
if not ran_now:
    shared = (st.session_state.get("pulse_approval") or {}).get("decision") == "y"
    with st.status(
        f"✓ Done in {seconds} seconds" if seconds else "✓ Done",
        state="complete",
        expanded=False,
    ):
        st.write(
            f"{summary.get('total', 0):,} reviews read. "
            + (
                "Approved, saved and drafted."
                if shared
                else "Nothing has been shared yet — the approval step is at the bottom "
                "of this page."
            )
        )

section("THE SHORT ANSWER")

fee = summary.get("fee", {}) or {}
fee_name = str(fee.get("name", ""))
fee_count = int(fee.get("count", 0))
top_themes = list(insights.get("top_themes", []))[:3]

if fee_name.startswith("Extra charges"):
    fee_line = (
        "💸 Most confusing charge: users think extra charges on top of brokerage "
        f"are ‘hidden’ ({fee_count} reviews)."
    )
else:
    fee_line = (
        "💸 Most confusing charge: users think the brokerage rate itself is too "
        f"high ({fee_count} reviews)."
    )

st.markdown(
    short_answer_html(
        [
            f"😟 {summary.get('negative_pct', 0)}% of recent reviews are negative "
            "(1–2 stars).",
            "🔥 Biggest problems: "
            + ", ".join(plain_theme(name) for name in top_themes)
            + ".",
            fee_line,
        ]
    ),
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# 3) what users are complaining about
# --------------------------------------------------------------------------

section("WHAT USERS ARE COMPLAINING ABOUT", "How many unhappy reviews each topic got.")

chart_rows = [
    (
        plain_theme(theme.get("name", "?")),
        int(theme.get("negative_count", 0)),
        theme.get("name") in top_themes,
    )
    for theme in insights.get("themes", [])
    if theme.get("name") != POSITIVE_THEME
]
chart_rows.sort(key=lambda row: (-row[1], row[0]))

if chart_rows:
    st.markdown(bar_chart_html(chart_rows), unsafe_allow_html=True)
    st.markdown(
        '<div class="caption">Green bars are the 3 biggest problems — the ones to '
        "fix first.</div>",
        unsafe_allow_html=True,
    )

quotes = insights.get("quotes", [])[:3]
if quotes:
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    for quote in quotes:
        st.markdown(review_card_html(quote), unsafe_allow_html=True)
    st.markdown(
        '<div class="caption">Real quotes, copied word-for-word from Play Store '
        "reviews.</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div class="caption">No usable quotes were found in this set of reviews.'
        "</div>",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------
# 4) the charge users do not understand
# --------------------------------------------------------------------------

section("THE CHARGE USERS DON’T UNDERSTAND")

st.warning(
    "**Users expect to pay only the brokerage, but also see DP charges and "
    "government/exchange charges, and call them ‘hidden charges’.**\n\n"
    f"Mentioned in **{fee_count} reviews**."
)

examples = fee.get("examples", [])[:3]
if examples:
    for example in examples:
        st.markdown(evidence_html(example), unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="caption">No short examples were found in this set of reviews.'
        "</div>",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------
# 5) ready-to-use outputs
# --------------------------------------------------------------------------

section("READY-TO-USE OUTPUTS", "Both documents are ready. Take whichever one you need.")

pulse = outputs["weekly_pulse"]
explainer = outputs["fee_explainer"]
pulse_words = len(pulse.split())

pulse_tab, explainer_tab = st.tabs(
    ["📰 Weekly update (for product team)", "💬 Customer explanation (for support team)"]
)

with pulse_tab:
    if outputs.get("llm_used"):
        st.markdown(badge(f"Written by AI · {pulse_words} words"), unsafe_allow_html=True)
    else:
        st.markdown(
            badge(f"Standard template · {pulse_words} words", "amber"),
            unsafe_allow_html=True,
        )
    st.markdown(pulse)
    st.download_button(
        "⬇️ Download the weekly update",
        data=pulse,
        file_name="weekly_pulse.md",
        mime="text/markdown",
    )

with explainer_tab:
    st.markdown(
        badge(f"Facts from Groww’s official pricing page · Last checked {LAST_CHECKED}"),
        unsafe_allow_html=True,
    )
    st.markdown(explainer)
    st.download_button(
        "⬇️ Download the customer explanation",
        data=explainer,
        file_name="fee_explainer.md",
        mime="text/markdown",
    )

# --------------------------------------------------------------------------
# 6) share it — needs your approval
# --------------------------------------------------------------------------

section("SHARE IT — NEEDS YOUR APPROVAL")

st.markdown(
    '<div class="section-note">If you approve, we will do 2 things. Nothing happens '
    "until you click Approve.</div>",
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="checklist">'
    '<div class="check"><span class="box">☐</span><span>📝 Save this week’s update '
    "to the team notes document</span></div>"
    '<div class="check"><span class="box">☐</span><span>✉️ Create an email draft '
    "for the team (it will NOT be sent)</span></div>"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(f"**Email subject:** {esc(subject)}")

approve_col, not_now_col = st.columns(2)
with approve_col:
    approve_clicked = st.button("✅ Approve & share", type="primary", width="stretch")
with not_now_col:
    not_now_clicked = st.button("❌ Not now", width="stretch")

if approve_clicked:
    try:
        with st.status("Saving and drafting…", expanded=True) as status:
            status.write("📝 Saving this week’s update to the team notes document…")
            append_to_doc(
                date=today,
                top_themes=top_themes,
                weekly_pulse=pulse,
                identified_fee_issue=fee_name,
                explanation_bullets=outputs["bullets"],
                source_links=outputs["source_links"],
            )
            status.write("✓ Saved to the team notes document")

            status.write("✉️ Creating the email draft (it will NOT be sent)…")
            create_email_draft(subject=subject, body=email_body(pulse, explainer))
            status.write("✓ Email draft created")

            log_decision("y", ["append_to_doc", "create_email_draft"])
            status.update(label="✅ Done", state="complete", expanded=False)
    except Exception as exc:  # noqa: BLE001 - keep the page alive
        st.error(f"Could not share the update ({type(exc).__name__}): {exc}")
    else:
        st.session_state["pulse_approval"] = {"decision": "y"}

elif not_now_clicked:
    log_decision("n", [])
    st.session_state["pulse_approval"] = {"decision": "n"}

approval = st.session_state.get("pulse_approval")

if approval and approval.get("decision") == "y":
    st.success(
        "Done! Saved to the notes document and created an email draft (not sent)."
    )
    st.balloons()

    with st.expander("📄 What was saved to the team notes document"):
        entry = latest_notes_entry()
        if entry:
            with st.container(border=True):
                st.markdown(entry)
        else:
            st.markdown(
                '<div class="caption">The entry could not be read back.</div>',
                unsafe_allow_html=True,
            )

    with st.expander("✉️ The email draft (not sent)"):
        if EMAIL_PATH.exists():
            headers, body = split_email(EMAIL_PATH.read_text(encoding="utf-8"))
            with st.container(border=True):
                st.markdown(
                    '<div class="email-head">'
                    f'<div><b>To:</b> {esc(headers.get("To", "—"))}</div>'
                    f'<div><b>Subject:</b> {esc(headers.get("Subject", "—"))}</div>'
                    f'<div><b>Status:</b> {esc(headers.get("Status", "DRAFT — NOT SENT"))}</div>'
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(body)
        else:
            st.markdown(
                '<div class="caption">The draft could not be read back.</div>',
                unsafe_allow_html=True,
            )

elif approval and approval.get("decision") == "n":
    st.info("Okay — nothing was saved or shared.")

st.markdown(
    '<div class="tech">Technical note: these 2 actions are MCP tools '
    "(append_to_doc, create_email_draft) in mcp_server.py, run only after human "
    "approval. Every decision is logged in outputs/approval_log.jsonl.</div>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# run again
# --------------------------------------------------------------------------

st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

if st.button("🔄 Run again", width="content"):
    clear_everything()
    st.session_state["pulse_auto_run"] = True
    st.rerun()

st.markdown(
    '<div class="caption">Run again clears the results and starts the week again.'
    "</div>",
    unsafe_allow_html=True,
)
