"""Streamlit web UI for the Groww review pulse workflow — a guided 5-step roadmap.

Run with:  streamlit run app.py

The page is a roadmap a first-time user can follow without any context:

    1 Collect reviews -> 2 Find themes -> 3 Spot fee confusion
    -> 4 Write outputs -> 5 Approve & share

It reuses the existing pipeline (analyze.py, generate.py, mcp_server.py)
without changing it:
  - "Analyze reviews"    -> run_analysis(), the keyword analysis over
                            data/reviews.csv
  - "Generate pulse"     -> make_outputs(), writes outputs/weekly_pulse.md and
                            outputs/fee_explainer.md
  - "Approve & run"      -> append_to_doc() + create_email_draft(), the only
                            place where outputs/notes_doc.md and
                            outputs/email_draft.md are written, and it only
                            happens after the user presses Approve
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from analyze import run_analysis
from generate import EXPLAINER_PATH, LAST_CHECKED, PULSE_PATH, make_outputs, stars
from mcp_server import append_to_doc, create_email_draft
from run_workflow import log_decision

try:  # the SDK is optional - without it the app falls back to template text
    from groq import Groq  # noqa: F401

    GROQ_AVAILABLE = True
except Exception:  # noqa: BLE001
    GROQ_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent
REVIEWS_CSV = BASE_DIR / "data" / "reviews.csv"
NOTES_PATH = BASE_DIR / "outputs" / "notes_doc.md"
EMAIL_PATH = BASE_DIR / "outputs" / "email_draft.md"
LOG_PATH = BASE_DIR / "outputs" / "approval_log.jsonl"

load_dotenv(BASE_DIR / ".env")

st.set_page_config(
    page_title="Groww Review Pulse",
    page_icon="📊",
    layout="wide",
)

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

STEPS: list[tuple[int, str]] = [
    (1, "Collect reviews"),
    (2, "Find themes"),
    (3, "Spot fee confusion"),
    (4, "Write outputs"),
    (5, "Approve & share"),
]

TREND_TEXT = {
    "rising": "↑ rising",
    "falling": "↓ falling",
    "stable": "→ steady",
}

FEE_EXPLANATION = (
    "Users expect to pay only brokerage, but also see DP charges and statutory "
    "charges and call them 'hidden charges'."
)

SOURCE_LINKS = [
    ("Groww pricing (official charges)", "https://groww.in/pricing"),
    ("Brokerage calculator", "https://groww.in/calculators/brokerage-calculator"),
    ("Regulatory information", "https://groww.in/regulatory-and-other-information"),
    ("Groww on Google Play", "https://play.google.com/store/apps/details?id=com.nextbillion.groww"),
]

# --------------------------------------------------------------------------
# styling
# --------------------------------------------------------------------------

CSS = """
<style>
  .stApp, [data-testid="stAppViewContainer"] {
    font-family: "Source Sans Pro", "Segoe UI", -apple-system, sans-serif;
  }

  /* ---------- hero ---------- */
  .pulse-hero { padding: 2px 0 0 0; }
  .pulse-hero h1 {
    font-size: 2.35rem; font-weight: 800; color: #1B1F23;
    margin: 0 0 6px 0; letter-spacing: -0.02em;
  }
  .pulse-sub {
    color: #6B7280; font-size: 1.02rem; line-height: 1.55;
    max-width: 960px; margin: 0 0 6px 0;
  }

  /* ---------- cards ---------- */
  .rc-card {
    background: #FFFFFF; border: 1px solid #E4EAE8; border-radius: 14px;
    padding: 15px 18px; margin: 4px 0 14px 0;
    box-shadow: 0 1px 2px rgba(16,24,40,.05), 0 10px 24px rgba(16,24,40,.05);
  }
  .rc-card.flat { background: #F4F7F6; box-shadow: none; border-color: #E4EAE8; }
  .rc-card.green { background: #F2FBF8; border-color: #B9E6D6; }
  .rc-card.amber { background: #FFFBF2; border-color: #F2D9A8; }

  /* Streamlit's own bordered containers get the same card look */
  [data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px; border: 1px solid #E4EAE8;
    box-shadow: 0 1px 2px rgba(16,24,40,.05), 0 10px 24px rgba(16,24,40,.05);
    background-color: #FFFFFF; padding: 6px 16px 12px 16px;
  }

  /* ---------- typography ---------- */
  .rc-step-title {
    font-size: 1.45rem; font-weight: 800; color: #1B1F23;
    margin: 4px 0 10px 0; letter-spacing: -0.01em;
  }
  .rc-label {
    font-size: .72rem; text-transform: uppercase; letter-spacing: .07em;
    color: #8A9490; font-weight: 700; margin-bottom: 4px;
  }
  .rc-caption { color: #6B7280; font-size: .84rem; line-height: 1.5; }
  .rc-body { color: #1B1F23; font-size: .95rem; line-height: 1.55; }

  /* ---------- metric cards ---------- */
  .rc-metric {
    background: #F4F7F6; border: 1px solid #E4EAE8; border-radius: 12px;
    padding: 12px 14px; margin-bottom: 10px;
  }
  .rc-metric .rc-label { margin-bottom: 5px; }
  .rc-metric .rc-value {
    font-size: 1.4rem; font-weight: 800; color: #1B1F23; line-height: 1.15;
  }
  .rc-metric .rc-note { font-size: .74rem; color: #8A9490; margin-top: 4px; }

  /* ---------- badges ---------- */
  .rc-badge {
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: .73rem; font-weight: 700;
    background: #E8F7F2; color: #0A7D5F; border: 1px solid #B9E6D6;
  }
  .rc-badge.grey { background: #F1F4F3; color: #5C6763; border-color: #E0E5E4; }
  .rc-badge.amber { background: #FFF4DC; color: #8A5B00; border-color: #F2D9A8; }

  /* ---------- roadmap ---------- */
  .rc-roadmap { display: flex; align-items: flex-start; width: 100%; margin: 12px 0 2px 0; }
  .rc-step { display: flex; flex-direction: column; align-items: center; min-width: 92px; }
  .rc-dot {
    width: 34px; height: 34px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: .92rem;
    background: #F1F4F3; color: #98A29E; border: 2px solid #E4EAE8;
  }
  .rc-step.done .rc-dot { background: #00B386; border-color: #00B386; color: #FFFFFF; }
  .rc-step.current .rc-dot {
    background: #FFFFFF; color: #00B386; border-color: #00B386;
    transform: scale(1.16); box-shadow: 0 0 0 6px rgba(0,179,134,.15);
  }
  .rc-step-label {
    margin-top: 10px; font-size: .78rem; color: #6B7280;
    text-align: center; line-height: 1.3;
  }
  .rc-step.done .rc-step-label { color: #2E7A63; }
  .rc-step.current .rc-step-label { color: #1B1F23; font-weight: 700; }
  .rc-connector {
    flex: 1 1 auto; height: 3px; background: #E4EAE8;
    margin: 15px 10px 0 10px; border-radius: 3px;
  }
  .rc-connector.done { background: #00B386; }

  /* ---------- horizontal bar chart ---------- */
  .rc-bar-row { display: flex; align-items: center; gap: 10px; margin: 7px 0; }
  .rc-bar-label { flex: 0 0 210px; font-size: .85rem; color: #1B1F23; }
  .rc-bar-track {
    flex: 1 1 auto; background: #F1F4F3; border-radius: 7px;
    height: 20px; overflow: hidden;
  }
  .rc-bar-fill { height: 100%; background: #C6D3CF; border-radius: 7px; }
  .rc-bar-fill.top { background: #00B386; }
  .rc-bar-value { flex: 0 0 46px; text-align: right; font-size: .85rem; font-weight: 700; }

  /* ---------- quote cards ---------- */
  .rc-quote {
    background: #FFFFFF; border: 1px solid #E4EAE8;
    border-left: 4px solid #00B386; border-radius: 12px;
    padding: 12px 15px; margin: 0 0 10px 0;
    box-shadow: 0 1px 2px rgba(16,24,40,.04);
  }
  .rc-quote.grey {
    background: #F7F9F9; border-left-color: #C6D3CF; box-shadow: none;
  }
  .rc-quote-top { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
  .rc-stars { color: #E8A33D; font-size: .95rem; letter-spacing: 1px; }
  .rc-quote-theme {
    font-size: .73rem; font-weight: 700; color: #0A7D5F;
    background: #E8F7F2; border-radius: 999px; padding: 2px 10px;
  }
  .rc-quote-text {
    font-style: italic; color: #1B1F23; font-size: .93rem; line-height: 1.55;
  }
  .rc-quote-meta { font-size: .76rem; color: #8A9490; margin-top: 8px; }

  /* ---------- action cards ---------- */
  .rc-action-title { font-size: 1rem; font-weight: 700; color: #1B1F23; }
  .rc-field { font-size: .82rem; color: #5C6763; margin: 4px 0; line-height: 1.45; }
  .rc-field b { color: #1B1F23; }

  /* ---------- sidebar ---------- */
  .side-step { font-size: .86rem; color: #6B7280; padding: 4px 0; }
  .side-step.current { color: #1B1F23; font-weight: 700; }
  .side-num {
    display: inline-block; width: 19px; height: 19px; line-height: 19px;
    text-align: center; border-radius: 50%; background: #F1F4F3;
    color: #8A9490; font-size: .68rem; font-weight: 700; margin-right: 7px;
  }
  .side-step.current .side-num { background: #00B386; color: #FFFFFF; }

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


def metric_card(label: str, value: str, note: str = "") -> str:
    note_html = f'<div class="rc-note">{esc(note)}</div>' if note else ""
    return (
        '<div class="rc-metric">'
        f'<div class="rc-label">{esc(label)}</div>'
        f'<div class="rc-value">{esc(value)}</div>'
        f"{note_html}"
        "</div>"
    )


def badge(text: str, style: str = "") -> str:
    css = f" {style}" if style else ""
    return f'<span class="rc-badge{css}">{esc(text)}</span>'


def roadmap_html(current: int) -> str:
    """The 5 circles connected by a line: done = green tick, current = big."""
    parts = ['<div class="rc-roadmap">']
    for index, (number, title) in enumerate(STEPS):
        if index:
            connector_done = number <= current
            parts.append(
                f'<div class="rc-connector{" done" if connector_done else ""}"></div>'
            )
        if number < current:
            css, dot = "done", "✓"
        elif number == current:
            css, dot = "current", str(number)
        else:
            css, dot = "", str(number)
        parts.append(
            f'<div class="rc-step {css}">'
            f'<div class="rc-dot">{dot}</div>'
            f'<div class="rc-step-label">{esc(title)}</div>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def what_happens(text: str) -> None:
    st.markdown(
        '<div class="rc-card flat">'
        '<div class="rc-label">What happens here</div>'
        f'<div class="rc-body">{esc(text)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def why_it_matters(text: str) -> None:
    st.markdown(
        f'<div class="rc-caption">💡 <b>Why it matters:</b> {esc(text)}</div>',
        unsafe_allow_html=True,
    )


def result_header(text: str = "Result") -> None:
    st.markdown(
        f'<div class="rc-label" style="color:#00B386;margin:14px 0 2px 0;">{esc(text)}</div>',
        unsafe_allow_html=True,
    )


def bar_chart_html(rows: list[tuple[str, int, bool]]) -> str:
    """A horizontal bar chart built in HTML so the top themes can be green."""
    biggest = max((value for _, value, _ in rows), default=0) or 1
    parts = []
    for label, value, is_top in rows:
        width = max(2.0, round(100 * value / biggest, 1))
        parts.append(
            '<div class="rc-bar-row">'
            f'<div class="rc-bar-label">{esc(label)}</div>'
            '<div class="rc-bar-track">'
            f'<div class="rc-bar-fill{" top" if is_top else ""}" style="width:{width}%"></div>'
            "</div>"
            f'<div class="rc-bar-value">{value}</div>'
            "</div>"
        )
    return "".join(parts)


def quote_card_html(quote: dict) -> str:
    rating = int(quote.get("rating", 0) or 0)
    return (
        '<div class="rc-quote">'
        '<div class="rc-quote-top">'
        f'<span class="rc-stars">{stars(rating)}</span>'
        f'<span class="rc-quote-theme">{esc(quote.get("theme", ""))}</span>'
        "</div>"
        f'<div class="rc-quote-text">“{esc(quote.get("short_quote", ""))}”</div>'
        f'<div class="rc-quote-meta">{rating} out of 5 stars · {esc(quote.get("date", ""))}'
        f' · {quote.get("thumbs_up", 0)} people found this helpful</div>'
        "</div>"
    )


def snippet_card_html(text: str) -> str:
    return (
        '<div class="rc-quote grey">'
        f'<div class="rc-quote-text">“{esc(text)}”</div>'
        "</div>"
    )


def email_body(pulse: str, explainer: str) -> str:
    """The same body run_workflow.py puts in the email draft."""
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
    """The most recent '## Entry —' block of outputs/notes_doc.md."""
    if not NOTES_PATH.exists():
        return ""
    text = NOTES_PATH.read_text(encoding="utf-8")
    marker = "## Entry —"
    parts = text.split(marker)
    if len(parts) <= 1:
        return text
    return marker + parts[-1]


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


def read_approval_log() -> list[dict]:
    """Every decision recorded in outputs/approval_log.jsonl."""
    if not LOG_PATH.exists():
        return []
    entries: list[dict] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


# --------------------------------------------------------------------------
# session state
# --------------------------------------------------------------------------

st.session_state.setdefault("step", 1)
st.session_state.setdefault("reviews", None)
st.session_state.setdefault("insights", None)
st.session_state.setdefault("outputs", None)
st.session_state.setdefault("approval", None)

current_step = int(st.session_state["step"])
today = date.today().isoformat()
subject = f"Weekly Product Pulse + Customer Clarification — {today}"


# --------------------------------------------------------------------------
# sidebar
# --------------------------------------------------------------------------

with st.sidebar:
    st.markdown("#### 🗺️ How it works")
    st.markdown(
        "".join(
            f'<div class="side-step{" current" if number == current_step else ""}">'
            f'<span class="side-num">{number}</span>{esc(title)}</div>'
            for number, title in STEPS
        ),
        unsafe_allow_html=True,
    )

    st.divider()

    st.markdown("#### 🤖 AI status")
    model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    if os.getenv("GROQ_API_KEY") and GROQ_AVAILABLE:
        st.markdown(
            badge(f"🟢 AI connected ({model_name})"), unsafe_allow_html=True
        )
        st.caption("The pulse wording is written by the AI model.")
    else:
        st.markdown(
            badge("🟡 AI unavailable — template mode", "amber"),
            unsafe_allow_html=True,
        )
        st.caption("No API key found, so the built-in template is used instead.")

    st.divider()

    st.markdown("#### 🔗 Sources")
    for label, link in SOURCE_LINKS:
        st.markdown(f"- [{label}]({link})")

    st.divider()
    st.caption(
        "Nothing is written to outputs/notes_doc.md or outputs/email_draft.md "
        "until you approve the actions in step 5."
    )


# --------------------------------------------------------------------------
# hero + roadmap (shown on every step)
# --------------------------------------------------------------------------

st.markdown(
    '<div class="pulse-hero">'
    "<h1>📊 Groww Review Pulse</h1>"
    '<div class="pulse-sub">Turns real Play Store reviews into a weekly product '
    "update and a customer-ready fee explanation — with human approval before "
    "anything is shared.</div>"
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(roadmap_html(current_step), unsafe_allow_html=True)
st.progress((current_step - 1) / 4)
st.markdown(
    f'<div class="rc-caption" style="margin-top:-6px;">Step {current_step} of 5 '
    f"— {esc(dict(STEPS)[current_step])}</div>",
    unsafe_allow_html=True,
)
st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# the steps
# --------------------------------------------------------------------------


def step_collect_reviews() -> None:
    what_happens(
        "We load public Google Play reviews of the Groww app from the last "
        "~12 weeks (data/reviews.csv)."
    )

    if st.button("📥 Load reviews", type="primary"):
        try:
            frame = pd.read_csv(REVIEWS_CSV)
            frame["date"] = pd.to_datetime(
                frame["date"], errors="coerce", format="%Y-%m-%d"
            )
            frame = frame.dropna(subset=["date"]).reset_index(drop=True)
            frame["rating"] = (
                pd.to_numeric(frame["rating"], errors="coerce").fillna(0).astype(int)
            )
            st.session_state["reviews"] = frame
        except Exception as exc:  # noqa: BLE001 - show the error, keep the app alive
            st.error(f"Could not load the reviews ({type(exc).__name__}): {exc}")

    frame = st.session_state.get("reviews")
    if frame is None or frame.empty:
        st.caption("Press **Load reviews** to start. Nothing else happens yet.")
        return

    result_header()

    total = int(len(frame))
    start = frame["date"].min().date().isoformat()
    end = frame["date"].max().date().isoformat()
    average = float(frame["rating"].mean())
    negative_pct = 100.0 * float((frame["rating"] <= 2).mean())

    metric_columns = st.columns(4)
    cards = [
        ("Total reviews", f"{total:,}", "from the last ~12 weeks"),
        ("Date range", f"{start} → {end}", "oldest → newest"),
        ("Average rating", f"{average:.2f} ★", "out of 5 stars"),
        ("% negative (1–2★)", f"{negative_pct:.0f}%", "reviews we call a problem"),
    ]
    for column, (label, value, note) in zip(metric_columns, cards):
        with column:
            st.markdown(metric_card(label, value, note), unsafe_allow_html=True)

    st.markdown("**How the ratings are spread out**")
    counts = frame["rating"].value_counts()
    ordered = [int(counts.get(star, 0)) for star in (1, 2, 3, 4, 5)]
    rating_chart = pd.DataFrame(
        {"Reviews": ordered}, index=[f"{star}★" for star in (1, 2, 3, 4, 5)]
    )
    st.bar_chart(rating_chart, color="#00B386", height=190, sort=False)

    with st.expander("Peek at raw reviews"):
        sample = (
            frame.assign(Date=frame["date"].dt.strftime("%Y-%m-%d"))
            .sort_values("date", ascending=False)
            .head(10)[["Date", "rating", "text"]]
            .rename(columns={"rating": "Rating", "text": "Review"})
        )
        st.dataframe(
            sample,
            hide_index=True,
            column_config={
                "Date": st.column_config.TextColumn("Date", width="small"),
                "Rating": st.column_config.NumberColumn("Rating", format="%d", width="small"),
                "Review": st.column_config.TextColumn("Review", width="large"),
            },
        )
        st.caption("These are the 10 most recent reviews, exactly as they came in.")

    why_it_matters(
        "Everything that follows is built on this set of reviews, so it is worth "
        "checking the size and the time span before moving on."
    )


def step_find_themes() -> None:
    what_happens(
        "Each review is tagged into one of 5 themes using keyword rules. The 3 "
        "themes with the most negative reviews are the top issues."
    )

    if st.button("🔍 Analyze reviews", type="primary"):
        with st.status("Analyzing…", expanded=True) as status:
            for label, note in [
                (
                    "Tagging reviews into themes…",
                    "Every review is matched against 5 keyword lists.",
                ),
                (
                    "Counting negative reviews…",
                    "Only 1★ and 2★ reviews count as negative.",
                ),
                (
                    "Picking top 3…",
                    "The 3 themes with the most negative reviews win.",
                ),
                (
                    "Selecting real user quotes…",
                    "One real review per top theme, copied word-for-word.",
                ),
            ]:
                status.update(label=label)
                status.write(note)
                time.sleep(0.35)
            try:
                insights = run_analysis()
            except (Exception, SystemExit) as exc:  # noqa: BLE001
                status.update(label=f"Analysis failed: {exc}", state="error")
            else:
                st.session_state["insights"] = insights
                status.update(label="✅ Analysis complete", state="complete")
                status.write(
                    f"{insights.get('total_reviews', 0)} reviews tagged into 5 themes."
                )

    insights = st.session_state.get("insights")
    if not insights:
        st.caption("Press **Analyze reviews** to find the themes.")
        return

    result_header()

    themes = insights.get("themes", [])
    top_themes = list(insights.get("top_themes", []))

    st.markdown("**Negative reviews per theme**")
    st.markdown(
        bar_chart_html(
            [
                (theme.get("name", "?"), int(theme.get("negative_count", 0)), theme.get("name") in top_themes)
                for theme in themes
            ]
        ),
        unsafe_allow_html=True,
    )
    st.caption("Green bars are the 3 top issues — the ones to fix first.")

    st.markdown("**The full theme table**")
    table_rows = [
        {
            "Theme": ("★ " if theme.get("name") in top_themes else "")
            + str(theme.get("name", "?")),
            "Reviews": int(theme.get("review_count", 0)),
            "Negative (1–2★)": int(theme.get("negative_count", 0)),
            "Trend": TREND_TEXT.get(str(theme.get("trend", "stable")), "→ steady"),
        }
        for theme in themes
    ]
    st.dataframe(
        pd.DataFrame(table_rows),
        hide_index=True,
        column_config={
            "Theme": st.column_config.TextColumn("Theme", width="medium"),
            "Reviews": st.column_config.NumberColumn("Reviews", format="%d"),
            "Negative (1–2★)": st.column_config.NumberColumn("Negative (1–2★)", format="%d"),
            "Trend": st.column_config.TextColumn("Trend", width="small"),
        },
    )
    st.caption("★ marks a top 3 theme. Trend compares this week with the weeks before it.")

    st.markdown("**What users actually said**")
    quotes = insights.get("quotes", [])[:3]
    if not quotes:
        st.caption("No usable quotes were found in this data set.")
    for quote in quotes:
        st.markdown(quote_card_html(quote), unsafe_allow_html=True)
    st.caption("Quotes are copied word-for-word from real reviews.")

    why_it_matters(
        "The top 3 themes are the weekly agenda. The quotes are the proof, so "
        "anyone can check them against the real reviews."
    )


def step_fee_confusion() -> None:
    what_happens(
        "Among charge-related reviews, we look for the most common misunderstanding "
        "about a fee."
    )

    insights = st.session_state.get("insights")
    if not insights:
        st.info("We need the analysis first — go back to step 2 and press **Analyze reviews**.")
        return

    result_header()

    fee = insights.get("fee_issue", {})
    name = str(fee.get("name", "Unknown fee issue"))
    count = int(fee.get("count", 0))
    counts = fee.get("counts", {}) or {}

    st.markdown(
        '<div class="rc-card amber">'
        '<div class="rc-label">⚠️ Fee issue spotted</div>'
        f'<div style="font-size:1.12rem;font-weight:800;color:#1B1F23;margin:6px 0 4px 0;">'
        f"{esc(name)}</div>"
        f'<div class="rc-body">mentioned in <b>{count} reviews</b></div>'
        "</div>",
        unsafe_allow_html=True,
    )

    others = ", ".join(
        f"{label}: {value} reviews" for label, value in counts.items() if label != name
    )
    if others:
        st.caption(f"Compared with the other fee bucket — {others}.")

    st.markdown(
        '<div class="rc-card flat">'
        '<div class="rc-label">In plain English</div>'
        f'<div class="rc-body">{esc(FEE_EXPLANATION)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    examples = fee.get("examples", [])[:3]
    if examples:
        st.markdown("**Evidence from real reviews**")
        for example in examples:
            st.markdown(snippet_card_html(example), unsafe_allow_html=True)
    else:
        st.caption("No fee snippets were found in this data set.")

    why_it_matters(
        "This is the one misunderstanding we explain to customers in step 4, so "
        "everyone hears the same, correct story about charges."
    )


def step_write_outputs() -> None:
    what_happens(
        "An AI model (Groq) writes the weekly product pulse from the analysis. The "
        "fee explainer uses only verified facts from Groww's official pricing page."
    )

    insights = st.session_state.get("insights")
    if not insights:
        st.info("We need the analysis first — go back to step 2 and press **Analyze reviews**.")
        return

    if st.button("✍️ Generate pulse & explainer", type="primary"):
        with st.status("Writing the outputs…", expanded=True) as status:
            status.update(label="Sending insights to the AI…")
            status.write("Only theme counts and quotes are sent — never raw reviews.")
            time.sleep(0.3)
            try:
                outputs = make_outputs(insights)
            except Exception as exc:  # noqa: BLE001
                status.update(label=f"Could not write the outputs: {exc}", state="error")
            else:
                PULSE_PATH.parent.mkdir(parents=True, exist_ok=True)
                PULSE_PATH.write_text(outputs["weekly_pulse"], encoding="utf-8")
                EXPLAINER_PATH.write_text(outputs["fee_explainer"], encoding="utf-8")
                st.session_state["outputs"] = outputs
                status.update(label="Checking the 250-word limit…")
                status.write(
                    f"The pulse is {len(outputs['weekly_pulse'].split())} words."
                )
                status.update(label="Building the fee explainer from official facts…")
                status.write(
                    f"{len(outputs['bullets'])} bullets taken from groww.in/pricing, "
                    f"last checked {LAST_CHECKED}."
                )
                status.update(label="✅ Both files written", state="complete")

    outputs = st.session_state.get("outputs")
    if not outputs:
        st.caption("Press **Generate pulse & explainer** to write both documents.")
        return

    result_header()

    pulse = outputs["weekly_pulse"]
    explainer = outputs["fee_explainer"]
    pulse_words = len(pulse.split())
    llm_used = bool(outputs.get("llm_used"))

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("#### 📰 Weekly Product Pulse (internal)")
            if llm_used:
                st.markdown(
                    badge(f"AI-written · {pulse_words} words"), unsafe_allow_html=True
                )
            else:
                st.markdown(
                    badge(f"Template · {pulse_words} words", "grey"),
                    unsafe_allow_html=True,
                )
            st.markdown(pulse)
            st.caption("For the product team — not sent to customers as it is.")

    with right:
        with st.container(border=True):
            st.markdown("#### 💬 Fee Explainer (for customers)")
            st.markdown(
                badge(f"Facts-only · Last checked {LAST_CHECKED}"),
                unsafe_allow_html=True,
            )
            st.markdown(explainer)
            st.caption("Reusable snippet — safe to copy into a support reply.")

    why_it_matters(
        "You now have two documents to look at. Nothing has been shared yet — "
        "step 5 asks for your approval first."
    )


def step_approve() -> None:
    what_happens(
        "Nothing is shared automatically. Review the 2 actions below. They only run "
        "after you approve."
    )

    insights = st.session_state.get("insights") or {}
    outputs = st.session_state.get("outputs") or {}

    if not outputs:
        st.info("We need the two documents first — go back to step 4 and press **Generate pulse & explainer**.")
        return

    result_header()

    top_themes = list(insights.get("top_themes", []))[:3]
    fee_name = str((insights.get("fee_issue", {}) or {}).get("name", ""))

    action_left, action_right = st.columns(2)
    with action_left:
        with st.container(border=True):
            st.markdown("#### 📝 Append to Notes Doc")
            st.markdown(
                '<div class="rc-field">Target file: <code>outputs/notes_doc.md</code></div>',
                unsafe_allow_html=True,
            )
            st.markdown("It adds one dated entry with:")
            st.markdown(
                "\n".join(
                    f"- {field}"
                    for field in [
                        "date",
                        "top themes",
                        "weekly pulse",
                        "fee issue",
                        "explanation bullets",
                        "source links",
                    ]
                )
            )
            st.caption(
                f"Today's entry would list: {', '.join(top_themes) or '—'} · {fee_name or '—'}"
            )

    with action_right:
        with st.container(border=True):
            st.markdown("#### ✉️ Create Email Draft")
            st.markdown(
                '<div class="rc-field">Target file: <code>outputs/email_draft.md</code></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="rc-field">Subject: <b>{esc(subject)}</b></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                badge("Draft only · will NOT be sent", "amber"), unsafe_allow_html=True
            )
            st.caption("The tool only saves a file. No email is ever sent.")

    st.markdown("")

    approve_col, reject_col = st.columns(2)
    with approve_col:
        approve_clicked = st.button(
            "✅ Approve & run", type="primary", width="stretch"
        )
    with reject_col:
        reject_clicked = st.button("❌ Reject", width="stretch")

    approval = st.session_state.get("approval")

    if approve_clicked:
        pulse = outputs["weekly_pulse"]
        with st.status("Running the approved actions…", expanded=True) as status:
            status.update(label="Calling MCP tool append_to_doc…")
            doc_result = append_to_doc(
                date=today,
                top_themes=top_themes,
                weekly_pulse=pulse,
                identified_fee_issue=fee_name,
                explanation_bullets=outputs["bullets"],
                source_links=outputs["source_links"],
            )
            status.write(doc_result)
            status.update(label="✅ append_to_doc finished")

            status.update(label="Calling MCP tool create_email_draft…")
            email_result = create_email_draft(
                subject=subject, body=email_body(pulse, outputs["fee_explainer"])
            )
            status.write(email_result)
            status.update(label="✅ create_email_draft finished")

            log_decision("y", ["append_to_doc", "create_email_draft"])
            status.update(
                label="✅ Decision recorded in outputs/approval_log.jsonl",
                state="complete",
            )
        st.session_state["approval"] = {
            "decision": "y",
            "doc_result": doc_result,
            "email_result": email_result,
        }
        approval = st.session_state["approval"]

    elif reject_clicked:
        log_decision("n", [])
        st.session_state["approval"] = {"decision": "n"}
        approval = st.session_state["approval"]

    if approval and approval.get("decision") == "y":
        st.success(
            "Done! Logged to the notes doc and created an email draft (not sent)."
        )
        st.balloons()

        notes_tab, email_tab = st.tabs(["📄 Notes Doc entry", "✉️ Email draft"])
        with notes_tab:
            entry = latest_notes_entry()
            if entry:
                st.markdown(entry)
            else:
                st.caption("No entry found in outputs/notes_doc.md yet.")

        with email_tab:
            if EMAIL_PATH.exists():
                headers, body = split_email(EMAIL_PATH.read_text(encoding="utf-8"))
                st.markdown(
                    '<div class="rc-card flat">'
                    f'<div class="rc-field"><b>To:</b> {esc(headers.get("To", "—"))}</div>'
                    f'<div class="rc-field"><b>Subject:</b> {esc(headers.get("Subject", "—"))}</div>'
                    f'<div class="rc-field"><b>Status:</b> {esc(headers.get("Status", "DRAFT — NOT SENT"))}</div>'
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(body)
            else:
                st.caption("No email draft file found.")
    elif approval and approval.get("decision") == "n":
        st.info("Cancelled — no actions were run, nothing was saved.")
        st.caption("The decision was recorded in outputs/approval_log.jsonl.")

    with st.expander("📜 Approval history"):
        entries = read_approval_log()
        if entries:
            history = [
                {
                    "When": entry.get("timestamp", "?"),
                    "Decision": "✅ Approved" if entry.get("answer") == "y" else "❌ Rejected",
                    "Actions run": ", ".join(entry.get("actions_run", [])) or "—",
                }
                for entry in reversed(entries)
            ]
            st.dataframe(
                pd.DataFrame(history),
                hide_index=True,
                column_config={
                    "When": st.column_config.TextColumn("When", width="medium"),
                    "Decision": st.column_config.TextColumn("Decision", width="small"),
                    "Actions run": st.column_config.TextColumn("Actions run", width="medium"),
                },
            )
        else:
            st.caption("No decisions recorded yet.")

    if st.button("🔄 Start over", width="content"):
        st.session_state["step"] = 1
        st.session_state["reviews"] = None
        st.session_state["insights"] = None
        st.session_state["outputs"] = None
        st.session_state["approval"] = None
        st.rerun()

    why_it_matters(
        "Approving only writes two local files — the notes doc entry and an email "
        "draft. The email is never sent, and you can start over at any time."
    )


STEP_FUNCTIONS = {
    1: step_collect_reviews,
    2: step_find_themes,
    3: step_fee_confusion,
    4: step_write_outputs,
    5: step_approve,
}

STEP_FUNCTIONS[current_step]()


# --------------------------------------------------------------------------
# navigation
# --------------------------------------------------------------------------


def can_move_forward() -> bool:
    """You can only continue once the current step has produced its result."""
    if current_step == 1:
        return st.session_state.get("reviews") is not None
    if current_step in (2, 3):
        return st.session_state.get("insights") is not None
    if current_step == 4:
        return st.session_state.get("outputs") is not None
    return False


st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

back_col, next_col = st.columns(2)
with back_col:
    if st.button(
        "⬅ Back",
        width="stretch",
        disabled=current_step <= 1,
        key="nav_back",
    ):
        st.session_state["step"] = max(1, current_step - 1)
        st.rerun()

with next_col:
    ready = can_move_forward()
    if st.button(
        "Next ➡",
        type="primary",
        width="stretch",
        disabled=current_step >= 5 or not ready,
        key="nav_next",
    ):
        st.session_state["step"] = min(5, current_step + 1)
        st.rerun()

if current_step < 5 and not ready:
    st.caption("Do the action on this step first — then you can move on.")
