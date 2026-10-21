"""Keyword based analysis of the Groww review CSV.

No API keys, no models - just regex keyword rules over data/reviews.csv.
Results are written to outputs/insights.json.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_CSV = BASE_DIR / "data" / "reviews.csv"
OUTPUT_JSON = BASE_DIR / "outputs" / "insights.json"

# Theme -> keywords. Matching is case insensitive and whole word only.
THEMES: dict[str, list[str]] = {
    "Charges & brokerage": [
        "charge",
        "charges",
        "brokerage",
        "brokrage",
        "fee",
        "fees",
        "hidden",
        "dp",
        "gst",
        "tax",
        "deduct",
        "expensive",
    ],
    "Customer support & withdrawals": [
        "support",
        "customer care",
        "customer service",
        "ticket",
        "withdraw",
        "withdrawal",
        "refund",
        "response",
    ],
    "App glitches & order issues": [
        "glitch",
        "crash",
        "slow",
        "lag",
        "stuck",
        "error",
        "stop loss",
        "order",
        "login",
        "otp",
    ],
    "Charts & features": [
        "chart",
        "charts",
        "indicator",
        "feature",
        "features",
        "watchlist",
        "interface",
    ],
    "Easy to use (positive)": [
        "easy",
        "simple",
        "user friendly",
        "beginner",
        "smooth",
    ],
}

POSITIVE_THEME = "Easy to use (positive)"

THIS_WEEK_DAYS = 7
RISING_FACTOR = 1.2
FALLING_FACTOR = 0.8

MIN_QUOTE_WORDS = 15
MAX_QUOTE_WORDS = 80
SHORT_QUOTE_MAX_CHARS = 160
SKIP_PHRASES = ("get your attention", "will change it later")

# Fee issue buckets.
EXTRA_CHARGE_LABEL = "Extra charges on top of brokerage (external + DP charges)"
HIGH_BROKERAGE_LABEL = "Brokerage rate too high"
EXTRA_CHARGE_PATTERNS = [
    r"hidden",
    r"external",
    r"other charges",
    r"dp",
    r"gst",
    r"tax",
]
HIGH_BROKERAGE_PATTERNS = [
    r"brokerage high|high brokerage",
    r"20\s*rs",
    r"per order",
]

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def build_pattern(keywords: list[str]) -> re.Pattern:
    """Whole word alternation for a keyword list (case insensitive)."""
    parts = [re.escape(kw) for kw in keywords]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


THEME_PATTERNS = {name: build_pattern(kws) for name, kws in THEMES.items()}


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def load_reviews(path: Path) -> list[dict]:
    reviews: list[dict] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                day = datetime.strptime(row["date"].strip(), "%Y-%m-%d").date()
            except (KeyError, ValueError):
                continue
            try:
                rating = int(float(row.get("rating") or 0))
            except (TypeError, ValueError):
                rating = 0
            try:
                thumbs_up = int(float(row.get("thumbs_up") or 0))
            except (TypeError, ValueError):
                thumbs_up = 0
            reviews.append(
                {
                    "review_id": (row.get("review_id") or "").strip(),
                    "date": day,
                    "rating": rating,
                    "thumbs_up": thumbs_up,
                    "text": row.get("text") or "",
                }
            )
    return reviews


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def week_start(day: date) -> date:
    """Monday of the week the date belongs to."""
    return day - timedelta(days=day.weekday())


def sentences(text: str) -> list[str]:
    """Split a review into sentences (newlines and sentence punctuation)."""
    parts: list[str] = []
    for block in text.splitlines():
        for chunk in SENTENCE_SPLIT.split(block):
            chunk = chunk.strip()
            if chunk:
                parts.append(chunk)
    return parts


def cut_at_word_boundary(text: str, limit: int) -> str:
    """Trim to `limit` characters on a word boundary and add an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-") + "…"


def first_sentence_with_keyword(text: str, pattern: re.Pattern) -> str | None:
    """First sentence that mentions the theme keyword, capped at 160 chars."""
    for sentence in sentences(text):
        if pattern.search(sentence):
            return cut_at_word_boundary(sentence, SHORT_QUOTE_MAX_CHARS)
    return None


def is_verbatim(text: str, snippet: str) -> bool:
    """Check that the snippet was copied word for word out of the text."""
    probe = snippet[:-1] if snippet.endswith("…") else snippet
    return probe.strip() in text


# --------------------------------------------------------------------------
# theme stats
# --------------------------------------------------------------------------


def theme_stats(reviews: list[dict]) -> list[dict]:
    """Per theme counts, last-7-days volume, earlier weekly average and trend."""
    if not reviews:
        return []

    last_day = max(r["date"] for r in reviews)
    first_day = min(r["date"] for r in reviews)
    this_week_start = last_day - timedelta(days=THIS_WEEK_DAYS - 1)
    earlier_end = this_week_start - timedelta(days=1)

    # Number of calendar weeks the earlier period spans.
    weeks_of_history = (
        (week_start(earlier_end) - week_start(first_day)).days // 7
    ) + 1

    stats: list[dict] = []
    for name, pattern in THEME_PATTERNS.items():
        hits = [r for r in reviews if pattern.search(r["text"])]
        negative = [r for r in hits if r["rating"] in (1, 2)]
        this_week = sum(1 for r in hits if r["date"] >= this_week_start)
        earlier = sum(1 for r in hits if r["date"] <= earlier_end)

        if weeks_of_history:
            weekly_avg_before = earlier / weeks_of_history
        else:
            weekly_avg_before = 0.0

        if this_week > weekly_avg_before * RISING_FACTOR:
            trend = "rising"
        elif this_week < weekly_avg_before * FALLING_FACTOR:
            trend = "falling"
        else:
            trend = "stable"

        stats.append(
            {
                "name": name,
                "review_count": len(hits),
                "negative_count": len(negative),
                "this_week": this_week,
                "weekly_avg_before": round(weekly_avg_before, 2),
                "trend": trend,
            }
        )

    stats.sort(key=lambda s: (-s["negative_count"], -s["review_count"], s["name"]))
    return stats


# --------------------------------------------------------------------------
# quotes
# --------------------------------------------------------------------------


def pick_quote(reviews: list[dict], theme: str) -> dict | None:
    """Highest thumbs up negative review of the theme that fits the filters."""
    pattern = THEME_PATTERNS[theme]
    candidates = [r for r in reviews if pattern.search(r["text"])]

    def usable(review: dict) -> bool:
        text = review["text"]
        if review["rating"] not in (1, 2):
            return False
        lowered = text.lower()
        if any(phrase in lowered for phrase in SKIP_PHRASES):
            return False
        words = len(text.split())
        return MIN_QUOTE_WORDS <= words <= MAX_QUOTE_WORDS

    pool = [r for r in candidates if usable(r)]
    relaxed = False
    if not pool:
        # Fall back to any negative review of the theme if the strict filters
        # (word count / canned replies) leave nothing behind.
        pool = [
            r
            for r in candidates
            if r["rating"] in (1, 2)
            and not any(p in r["text"].lower() for p in SKIP_PHRASES)
        ]
        relaxed = True
    if not pool:
        return None

    best = max(pool, key=lambda r: (r["thumbs_up"], r["date"]))
    short_quote = first_sentence_with_keyword(best["text"], pattern)
    if short_quote is None:
        short_quote = cut_at_word_boundary(best["text"].strip(), SHORT_QUOTE_MAX_CHARS)

    if not is_verbatim(best["text"], short_quote):
        raise AssertionError(f"short quote is not verbatim for review {best['review_id']}")

    return {
        "theme": theme,
        "date": best["date"].isoformat(),
        "rating": best["rating"],
        "thumbs_up": best["thumbs_up"],
        "text": best["text"],
        "short_quote": short_quote,
        "relaxed_filter": relaxed,
    }


# --------------------------------------------------------------------------
# fee issue
# --------------------------------------------------------------------------


def find_fee_issue(reviews: list[dict]) -> dict:
    """Compare 'extra charges' vs 'brokerage too high' inside the charges theme."""
    charges_reviews = [
        r for r in reviews if THEME_PATTERNS["Charges & brokerage"].search(r["text"])
    ]

    extra_pattern = re.compile(
        r"\b(?:" + "|".join(EXTRA_CHARGE_PATTERNS) + r")\b", re.IGNORECASE
    )
    brokerage_pattern = re.compile(
        r"\b(?:" + "|".join(HIGH_BROKERAGE_PATTERNS) + r")\b", re.IGNORECASE
    )

    extra_hits = [r for r in charges_reviews if extra_pattern.search(r["text"])]
    brokerage_hits = [r for r in charges_reviews if brokerage_pattern.search(r["text"])]

    candidates = [
        (EXTRA_CHARGE_LABEL, len(extra_hits), extra_pattern, extra_hits),
        (HIGH_BROKERAGE_LABEL, len(brokerage_hits), brokerage_pattern, brokerage_hits),
    ]
    name, count, pattern, hits = max(candidates, key=lambda c: (c[1], c[0]))

    examples: list[str] = []
    for review in sorted(hits, key=lambda r: (-r["thumbs_up"], r["date"])):
        snippet = first_sentence_with_keyword(review["text"], pattern)
        if snippet and is_verbatim(review["text"], snippet):
            examples.append(snippet)
        if len(examples) == 3:
            break

    return {
        "name": name,
        "count": count,
        "counts": {
            EXTRA_CHARGE_LABEL: len(extra_hits),
            HIGH_BROKERAGE_LABEL: len(brokerage_hits),
        },
        "examples": examples,
    }


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------


def run_analysis() -> dict:
    """Read the review CSV, analyse it and return the insights dict."""
    reviews = load_reviews(INPUT_CSV)
    if not reviews:
        raise SystemExit(f"No reviews found in {INPUT_CSV}")

    days = sorted({r["date"] for r in reviews})
    stats = theme_stats(reviews)
    top_themes = [
        s["name"]
        for s in sorted(
            [s for s in stats if s["name"] != POSITIVE_THEME],
            key=lambda s: (-s["negative_count"], -s["review_count"], s["name"]),
        )[:3]
    ]

    quotes = [q for q in (pick_quote(reviews, theme) for theme in top_themes) if q]

    return {
        "date_range": {"start": days[0].isoformat(), "end": days[-1].isoformat()},
        "total_reviews": len(reviews),
        "themes": stats,
        "top_themes": top_themes,
        "quotes": quotes,
        "fee_issue": find_fee_issue(reviews),
    }


def print_summary(results: dict) -> None:
    print("Groww review pulse - keyword analysis")
    print(f"Date range      : {results['date_range']['start']} -> {results['date_range']['end']}")
    print(f"Total reviews   : {results['total_reviews']}")

    print("\nThemes (review_count / negative_count / this_week / avg before / trend)")
    for theme in results["themes"]:
        print(
            f"  - {theme['name']:<34} {theme['review_count']:>5} "
            f"{theme['negative_count']:>5} {theme['this_week']:>5} "
            f"{theme['weekly_avg_before']:>7} {theme['trend']}"
        )

    print("\nTop themes")
    for index, name in enumerate(results["top_themes"], start=1):
        print(f"  {index}. {name}")

    print("\nQuotes")
    for quote in results["quotes"]:
        print(f"  [{quote['theme']}] {quote['date']} | rating {quote['rating']} | {quote['thumbs_up']} thumbs up")
        print(f"    {quote['short_quote']}")

    fee = results["fee_issue"]
    print(f"\nFee issue: {fee['name']} ({fee['count']} reviews)")
    for label, count in fee["counts"].items():
        print(f"    {label}: {count}")
    for example in fee["examples"]:
        print(f"    - {example}")


def main() -> None:
    results = run_analysis()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON.open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False)
    print_summary(results)
    print(f"\nSaved insights to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
