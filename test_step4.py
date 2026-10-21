"""Step 4 checks for outputs produced by generate.py.

Run with:  python test_step4.py
Exits with code 1 when any check fails.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PULSE_PATH = BASE_DIR / "outputs" / "weekly_pulse.md"
EXPLAINER_PATH = BASE_DIR / "outputs" / "fee_explainer.md"
INSIGHTS_PATH = BASE_DIR / "outputs" / "insights.json"
GITIGNORE_PATH = BASE_DIR / ".gitignore"

MAX_PULSE_WORDS = 250
REQUIRED_SECTIONS = ["Top themes", "What users say", "Key observation", "Action ideas"]
REQUIRED_LINKS = [
    "https://groww.in/pricing",
    "https://groww.in/calculators/brokerage-calculator",
]
MAX_BULLETS = 6


def count_words(text: str) -> int:
    return len(text.split())


def bullet_count(text: str) -> int:
    count = 0
    in_sources = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("sources:"):
            in_sources = True
            continue
        if in_sources and stripped and not (stripped[0].isdigit() or stripped.startswith("-") or stripped.startswith("*")):
            break
        if in_sources:
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            count += 1
    return count


def numbered_action_count(text: str) -> int:
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and stripped[0].isdigit():
            if stripped[1:3].lstrip(" ").startswith("."):
                count += 1
    return count


def load_insights() -> dict:
    with INSIGHTS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read(path: Path) -> str:
    return path.open("r", encoding="utf-8").read()


def main() -> int:
    print("=" * 72)
    print("STEP 4 TESTS - outputs/weekly_pulse.md & outputs/fee_explainer.md")
    print("=" * 72)
    print()

    passed = 0
    total = 7

    # a) weekly_pulse exists and at most 250 words
    try:
        if not PULSE_PATH.exists():
            raise AssertionError(f"file not found: {PULSE_PATH}")
        pulse = read(PULSE_PATH)
        words = count_words(pulse)
        assert words <= MAX_PULSE_WORDS, f"{words} words (limit {MAX_PULSE_WORDS})"
        print(f"PASS  a) weekly_pulse.md exists and <= {MAX_PULSE_WORDS} words ({words} words)")
        passed += 1
    except AssertionError as exc:
        print(f"FAIL  a) weekly_pulse.md exists and <= {MAX_PULSE_WORDS} words\n      {exc}")

    # b) required sections
    try:
        pulse = read(PULSE_PATH)
        missing = [s for s in REQUIRED_SECTIONS if s not in pulse]
        assert not missing, f"missing section(s): {missing}"
        print(f"PASS  b) sections present: {', '.join(REQUIRED_SECTIONS)}")
        passed += 1
    except AssertionError as exc:
        print(f"FAIL  b) sections present: {', '.join(REQUIRED_SECTIONS)}\n      {exc}")
    except FileNotFoundError as exc:
        print(f"FAIL  b) sections present: {', '.join(REQUIRED_SECTIONS)}\n      {exc}")

    # c) exactly 3 numbered action ideas
    try:
        pulse = read(PULSE_PATH)
        count = numbered_action_count(pulse)
        assert count == 3, f"found {count} numbered ideas, expected exactly 3"
        print(f"PASS  c) exactly 3 numbered action ideas ({count})")
        passed += 1
    except AssertionError as exc:
        print(f"FAIL  c) exactly 3 numbered action ideas\n      {exc}")
    except FileNotFoundError as exc:
        print(f"FAIL  c) exactly 3 numbered action ideas\n      {exc}")

    # d) each short_quote appears word-for-word
    try:
        if not INSIGHTS_PATH.exists():
            raise AssertionError(f"insights.json not found at {INSIGHTS_PATH}")
        insights = load_insights()
        pulse = read(PULSE_PATH)
        quotes = insights.get("quotes", [])
        assert len(quotes) == 3, f"expected 3 quotes in insights.json, found {len(quotes)}"
        for index, quote in enumerate(quotes, start=1):
            short = quote.get("short_quote", "")
            assert short.strip(), f"quote #{index} has empty short_quote"
            assert short in pulse, f"quote #{index} short_quote not found word-for-word in weekly_pulse.md"
            print(f"      quote #{index} found verbatim: {short[:80]!r}")
        print(f"PASS  d) all 3 short_quotes appear word-for-word in weekly_pulse.md")
        passed += 1
    except AssertionError as exc:
        print(f"FAIL  d) all 3 short_quotes appear word-for-word in weekly_pulse.md\n      {exc}")
    except FileNotFoundError as exc:
        print(f"FAIL  d) all 3 short_quotes appear word-for-word in weekly_pulse.md\n      {exc}")

    # e) fee issue name or "charges" and mention count
    try:
        insights = load_insights()
        pulse = read(PULSE_PATH)
        fee = insights.get("fee_issue", {})
        name = fee.get("name", "")
        count = fee.get("count")
        lower = pulse.lower()
        assert name and count is not None, "fee_issue missing name/count in insights.json"
        mentioned = name.lower() in lower or "charges" in lower
        assert mentioned, "weekly_pulse.md does not mention the fee issue or 'charges'"
        assert str(count) in pulse, f"mention count {count} not found in weekly_pulse.md"
        print(f"PASS  e) fee issue mentioned with count {count} ('{name}')")
        passed += 1
    except AssertionError as exc:
        print(f"FAIL  e) fee issue mentioned with count\n      {exc}")
    except FileNotFoundError as exc:
        print(f"FAIL  e) fee issue mentioned with count\n      {exc}")

    # f) fee_explainer checks
    try:
        if not EXPLAINER_PATH.exists():
            raise AssertionError(f"file not found: {EXPLAINER_PATH}")
        explainer = read(EXPLAINER_PATH)
        bcount = bullet_count(explainer)
        assert bcount <= MAX_BULLETS, f"{bcount} bullet points (max {MAX_BULLETS})"
        for link in REQUIRED_LINKS:
            assert link in explainer, f"missing link: {link}"
        assert "Last checked:" in explainer, "missing 'Last checked:'"
        print(f"PASS  f) fee_explainer.md: {bcount} bullets, both links present, Last checked: present")
        passed += 1
    except AssertionError as exc:
        print(f"FAIL  f) fee_explainer.md checks\n      {exc}")

    # g) .env in .gitignore and API key not in any .md file
    try:
        assert GITIGNORE_PATH.exists(), f".gitignore not found at {GITIGNORE_PATH}"
        gitignore = read(GITIGNORE_PATH)
        assert ".env" in gitignore, ".env not listed in .gitignore"
        api_key = __import__("os").environ.get("GROQ_API_KEY", "")
        leaked = []
        for md in BASE_DIR.glob("**/*.md"):
            content = read(md)
            if api_key and len(api_key) >= 8 and api_key in content:
                leaked.append(str(md.relative_to(BASE_DIR)))
        assert not leaked, f"API key leaked in: {leaked}"
        print("PASS  g) .env in .gitignore and no API key found in .md files")
        passed += 1
    except AssertionError as exc:
        print(f"FAIL  g) .gitignore/env safety\n      {exc}")

    print()
    print("=" * 72)
    print(f"STEP 4 TESTS: {passed}/{total} passed")
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
