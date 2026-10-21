"""Step 3 checks for outputs/insights.json produced by analyze.py.

Run with:  python test_step3.py
Exits with code 1 when any check fails.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
INSIGHTS_PATH = BASE_DIR / "outputs" / "insights.json"
REVIEWS_PATH = BASE_DIR / "data" / "reviews.csv"

ELLIPSIS = "\u2026"
POSITIVE_THEME = "Easy to use (positive)"
VALID_TRENDS = {"rising", "falling", "stable"}
MIN_THEMES, MAX_THEMES = 1, 5
EXPECTED_TOP_THEMES = 3
EXPECTED_QUOTES = 3
EXPECTED_EXAMPLES = 3
REQUIRED_COLUMNS = ["review_id", "date", "rating", "thumbs_up", "text"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def pick_key(mapping: object, *names: str):
    """Return the first present key out of `names`, or None."""
    if not isinstance(mapping, dict):
        return None
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def require(mapping: object, names: tuple[str, ...], context: str):
    """Return a value or raise a readable AssertionError instead of KeyError."""
    value = pick_key(mapping, *names)
    if value is None:
        raise AssertionError(
            f"{context}: missing key, expected one of {list(names)} "
            f"(found keys: {sorted(mapping) if isinstance(mapping, dict) else 'n/a'})"
        )
    return value


def load_insights() -> dict:
    with INSIGHTS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_reviews() -> pd.DataFrame:
    return pd.read_csv(REVIEWS_PATH, encoding="utf-8")


def review_texts() -> list[str]:
    frame = load_reviews()
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise AssertionError(
            f"{REVIEWS_PATH.name}: missing column(s) {missing} "
            f"(found: {list(frame.columns)})"
        )
    return [str(v) for v in frame["text"].fillna("")]


def contains_verbatim(texts: list[str], needle: str) -> bool:
    """True when `needle` shows up word-for-word in one of the review texts."""
    probe = needle.strip()
    if not probe:
        return False
    return any(probe in text for text in texts)


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


def test_a_themes_count(insights: dict, texts: list[str]) -> str:
    themes = require(insights, ("themes",), "insights.json")
    assert isinstance(themes, list), f"'themes' should be a list, got {type(themes).__name__}"
    count = len(themes)
    assert MIN_THEMES <= count <= MAX_THEMES, (
        f"expected between {MIN_THEMES} and {MAX_THEMES} themes, found {count}"
    )
    names = [t.get("name", "?") for t in themes if isinstance(t, dict)]
    return f"{count} themes ({', '.join(names)})"


def test_b_top_themes(insights: dict, texts: list[str]) -> str:
    tops = require(insights, ("top_themes", "themes_top"), "insights.json")
    assert isinstance(tops, list), f"'top_themes' should be a list, got {type(tops).__name__}"
    assert len(tops) == EXPECTED_TOP_THEMES, (
        f"expected exactly {EXPECTED_TOP_THEMES} top themes, found {len(tops)}"
    )
    assert POSITIVE_THEME not in tops, (
        f"positive theme '{POSITIVE_THEME}' must not be a top theme"
    )
    return " | ".join(str(t) for t in tops)


def test_c_quote_count(insights: dict, texts: list[str]) -> str:
    quotes = require(insights, ("quotes",), "insights.json")
    assert isinstance(quotes, list), f"'quotes' should be a list, got {type(quotes).__name__}"
    assert len(quotes) == EXPECTED_QUOTES, (
        f"expected exactly {EXPECTED_QUOTES} quotes, found {len(quotes)}"
    )
    return f"{len(quotes)} quotes"


def test_d_quotes_are_real(insights: dict, texts: list[str]) -> str:
    quotes = require(insights, ("quotes",), "insights.json")
    assert isinstance(quotes, list) and quotes, "'quotes' is empty"

    for index, quote in enumerate(quotes, start=1):
        assert isinstance(quote, dict), f"quote #{index} is not an object"
        full = require(quote, ("text", "quote", "body"), f"quote #{index}")
        short = require(quote, ("short_quote", "short", "snippet"), f"quote #{index}")
        theme = quote.get("theme", "?")

        assert isinstance(full, str) and full.strip(), f"quote #{index} has empty 'text'"
        assert isinstance(short, str) and short.strip(), f"quote #{index} has empty 'short_quote'"

        full_stripped = full.strip()
        if not any(t.strip() == full_stripped for t in texts):
            assert contains_verbatim(texts, full_stripped), (
                f"quote #{index} ({theme}) full text is not in reviews.csv"
            )

        probe = short[:-1] if short.endswith(ELLIPSIS) else short
        assert contains_verbatim(texts, probe), (
            f"quote #{index} ({theme}) short_quote is not verbatim in reviews.csv"
        )

        print(f"      quote #{index} [{theme}] short_quote: {probe[:90]!r}")

    return f"{len(quotes)} quotes verified verbatim"


def test_e_quote_ratings(insights: dict, texts: list[str]) -> str:
    quotes = require(insights, ("quotes",), "insights.json")
    assert isinstance(quotes, list) and quotes, "'quotes' is empty"

    ratings: list[int] = []
    for index, quote in enumerate(quotes, start=1):
        rating = require(quote, ("rating", "score", "stars"), f"quote #{index}")
        try:
            rating_value = int(float(rating))
        except (TypeError, ValueError):
            raise AssertionError(f"quote #{index} rating is not numeric: {rating!r}")
        assert rating_value in (1, 2), (
            f"quote #{index} rating should be 1 or 2, got {rating_value}"
        )
        ratings.append(rating_value)

    return "ratings: " + ", ".join(str(r) for r in ratings)


def test_f_fee_issue(insights: dict, texts: list[str]) -> str:
    fee = require(insights, ("fee_issue", "fee", "fee_problem"), "insights.json")
    assert isinstance(fee, dict), f"'fee_issue' should be an object, got {type(fee).__name__}"

    name = require(fee, ("name", "issue", "title", "label"), "fee_issue")
    count = require(fee, ("count", "mention_count", "review_count", "n"), "fee_issue")

    assert isinstance(name, str) and name.strip(), "fee_issue name is empty"
    try:
        count_value = int(count)
    except (TypeError, ValueError):
        raise AssertionError(f"fee_issue count is not numeric: {count!r}")
    assert count_value > 0, f"fee_issue count should be > 0, got {count_value}"

    print(f"      fee issue: {name} (count {count_value})")
    return f"{name} (count {count_value})"


def test_g_fee_evidence(insights: dict, texts: list[str]) -> str:
    fee = require(insights, ("fee_issue", "fee", "fee_problem"), "insights.json")
    assert isinstance(fee, dict), f"'fee_issue' should be an object, got {type(fee).__name__}"

    examples = require(fee, ("examples", "snippets", "example_snippets"), "fee_issue")
    assert isinstance(examples, list), f"fee_issue examples should be a list, got {type(examples).__name__}"
    assert len(examples) == EXPECTED_EXAMPLES, (
        f"expected {EXPECTED_EXAMPLES} example snippets, found {len(examples)}"
    )

    for index, example in enumerate(examples, start=1):
        assert isinstance(example, str) and example.strip(), (
            f"example #{index} is empty"
        )
        probe = example[:-1] if example.endswith(ELLIPSIS) else example
        assert contains_verbatim(texts, probe), (
            f"example #{index} snippet is not verbatim in reviews.csv: {probe[:90]!r}"
        )
        print(f"      example #{index}: {probe[:90]!r}")

    return f"{len(examples)} snippets verified verbatim"


def test_h_trends(insights: dict, texts: list[str]) -> str:
    themes = require(insights, ("themes",), "insights.json")
    assert isinstance(themes, list) and themes, "'themes' is empty"

    trends: list[str] = []
    for index, theme in enumerate(themes, start=1):
        assert isinstance(theme, dict), f"theme #{index} is not an object"
        trend = require(theme, ("trend",), f"theme #{index} ({theme.get('name', '?')})")
        assert isinstance(trend, str), f"theme #{index} trend is not a string: {trend!r}"
        assert trend in VALID_TRENDS, (
            f"theme #{index} trend '{trend}' is not one of {sorted(VALID_TRENDS)}"
        )
        trends.append(f"{theme.get('name', '?')}={trend}")

    return ", ".join(trends)


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------

CHECKS = [
    ("Themes (1-5 themes)", test_a_themes_count),
    ("Top themes (3, positive excluded)", test_b_top_themes),
    ("Quotes (3 quotes)", test_c_quote_count),
    ("Real quotes (verbatim in reviews.csv)", test_d_quotes_are_real),
    ("Quote ratings (1 or 2)", test_e_quote_ratings),
    ("Fee issue (name + count > 0)", test_f_fee_issue),
    ("Fee evidence (3 verbatim snippets)", test_g_fee_evidence),
    ("Trends (rising/falling/stable)", test_h_trends),
]


def main() -> int:
    print("=" * 72)
    print("STEP 3 TESTS - outputs/insights.json")
    print("=" * 72)

    if not INSIGHTS_PATH.exists():
        print(f"FAIL  insights.json not found at {INSIGHTS_PATH}")
        print("\nSTEP 3 TESTS: 0/8 passed")
        return 1
    if not REVIEWS_PATH.exists():
        print(f"FAIL  reviews.csv not found at {REVIEWS_PATH}")
        print("\nSTEP 3 TESTS: 0/8 passed")
        return 1

    insights = load_insights()
    print(f"\nKeys found in insights.json: {sorted(insights)}")
    print(f"total_reviews: {insights.get('total_reviews', '<missing>')}")
    print(f"date_range  : {insights.get('date_range', '<missing>')}")
    print(f"top_themes  : {insights.get('top_themes', '<missing>')}\n")

    try:
        texts = review_texts()
    except AssertionError as exc:
        print(f"FAIL  reviews.csv could not be read: {exc}")
        print("\nSTEP 3 TESTS: 0/8 passed")
        return 1

    print(f"Loaded {len(texts)} review texts from {REVIEWS_PATH.name}\n")

    passed = 0
    for label, check in CHECKS:
        try:
            detail = check(insights, texts)
        except AssertionError as exc:
            print(f"FAIL  {label}\n      {exc}")
        except Exception as exc:  # noqa: BLE001 - report instead of crashing
            print(f"FAIL  {label}\n      unexpected {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS  {label}")
            if detail:
                print(f"      {detail}")

    total = len(CHECKS)
    print("\n" + "=" * 72)
    print(f"STEP 3 TESTS: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
