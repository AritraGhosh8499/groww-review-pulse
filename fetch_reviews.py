"""Download Google Play reviews for the Groww app into data/reviews.csv.

Pulls the newest reviews for com.nextbillion.groww (lang=en, country=in),
keeps the ones from the last 12 weeks that carry at least 6 words, samples at
most 150 random reviews per week and masks phone numbers before writing CSV.
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from google_play_scraper import Sort, reviews

APP_ID = "com.nextbillion.groww"
LANG = "en"
COUNTRY = "in"

# Defaults required by the brief.
FETCH_COUNT = 200
WEEKS_BACK = 12
MIN_WORDS = 6
MAX_PER_WEEK = 150
RANDOM_SEED = 42

# Small politeness delay between page requests.
REQUEST_DELAY = 0.5
# Hard stop in case the continuation token keeps handing back the same page.
MAX_PAGES = 500

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE_DIR / "data" / "reviews.csv"

COLUMNS = ["review_id", "date", "rating", "thumbs_up", "text"]

# 10 digit phone numbers, optionally with an Indian country/trunk prefix and
# spaces or dashes between the digit groups ("98765 43210", "+91 9876543210").
PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+?91|0)[\s\-]?)?(?:\d[\s\-]?){9}\d(?!\d)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weeks", type=int, default=WEEKS_BACK, help="weeks of history to keep")
    parser.add_argument("--per-week", type=int, default=MAX_PER_WEEK, help="max reviews kept per week")
    parser.add_argument("--min-words", type=int, default=MIN_WORDS, help="minimum words in a review")
    parser.add_argument("--fetch-count", type=int, default=FETCH_COUNT, help="reviews requested per page")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="seed for the per week sampling")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help="seconds to wait between pages")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES, help="maximum number of pages to fetch")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="output CSV path")
    return parser.parse_args()


def mask_phone_numbers(text: str) -> str:
    """Replace 10 digit phone numbers with the literal ``[number]``."""
    return PHONE_RE.sub("[number]", text)


def review_date(review: dict) -> datetime | None:
    value = review.get("at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def week_start(dt: datetime) -> datetime:
    """Monday 00:00 of the ISO week the timestamp belongs to."""
    return datetime.combine(dt.date() - timedelta(days=dt.weekday()), datetime.min.time())


def fetch_reviews(cutoff: datetime, fetch_count: int, delay: float, max_pages: int) -> list[dict]:
    """Page through the newest reviews until the window is exhausted."""
    continuation_token = None
    seen_ids: set[str] = set()
    collected: list[dict] = []
    page = 0

    while page < max_pages:
        page += 1
        result, continuation_token = reviews(
            APP_ID,
            lang=LANG,
            country=COUNTRY,
            sort=Sort.NEWEST,
            count=fetch_count,
            continuation_token=continuation_token,
        )

        if not result:
            print(f"[page {page}] no more reviews returned, stopping")
            break

        oldest = None
        newest = None
        for review in result:
            dt = review_date(review)
            if dt is None:
                continue
            oldest = dt if oldest is None or dt < oldest else oldest
            newest = dt if newest is None or dt > newest else newest

            review_id = review.get("reviewId")
            if review_id and review_id in seen_ids:
                continue
            if review_id:
                seen_ids.add(review_id)

            if dt >= cutoff:
                collected.append(review)

        print(
            f"[page {page}] fetched {len(result)} reviews | kept {len(collected)} in window"
            f" | newest {newest:%Y-%m-%d} | oldest {oldest:%Y-%m-%d}"
        )

        # The feed is sorted newest first, so once the oldest review of a page
        # is older than the cutoff everything after it is out of the window.
        if oldest is not None and oldest < cutoff:
            print(f"[page {page}] reached the {cutoff:%Y-%m-%d} cutoff, stopping")
            break

        if continuation_token is None or continuation_token.token is None:
            print(f"[page {page}] continuation token exhausted, stopping")
            break

        if delay:
            time.sleep(delay)

    return collected


def filter_and_clean(reviews_in_window: list[dict], min_words: int) -> list[dict]:
    """Drop short reviews and mask phone numbers in the remaining ones."""
    rows = []
    for review in reviews_in_window:
        text = (review.get("content") or "").strip()
        if len(text.split()) < min_words:
            continue
        dt = review_date(review)
        if dt is None:
            continue
        rows.append(
            {
                "review_id": review.get("reviewId") or "",
                "date": dt.strftime("%Y-%m-%d"),
                "rating": review.get("score"),
                "thumbs_up": review.get("thumbsUpCount") or 0,
                "text": mask_phone_numbers(text),
            }
        )
    return rows


def sample_per_week(rows: list[dict], per_week: int, seed: int) -> list[dict]:
    """Keep at most ``per_week`` randomly chosen reviews for every week."""
    buckets: dict[datetime, list[dict]] = defaultdict(list)
    for row in rows:
        dt = datetime.strptime(row["date"], "%Y-%m-%d")
        buckets[week_start(dt)].append(row)

    random.seed(seed)
    kept: list[dict] = []
    for week in sorted(buckets):
        bucket = buckets[week]
        if len(bucket) > per_week:
            bucket = random.sample(bucket, per_week)
        kept.extend(bucket)
    return kept


def save_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    cutoff = datetime.now() - timedelta(weeks=args.weeks)

    print(f"Fetching reviews for {APP_ID} (lang={LANG}, country={COUNTRY})")
    print(f"Window: {cutoff:%Y-%m-%d} -> now ({args.weeks} weeks)")

    raw = fetch_reviews(cutoff, args.fetch_count, args.delay, args.max_pages)
    print(f"Fetched {len(raw)} reviews inside the window")

    rows = filter_and_clean(raw, args.min_words)
    print(f"{len(rows)} reviews left after the {args.min_words} word filter")

    kept = sample_per_week(rows, args.per_week, args.seed)
    kept.sort(key=lambda row: (row["date"], row["review_id"]), reverse=True)

    save_csv(kept, args.out)
    print(f"Saved {len(kept)} rows to {args.out}")


if __name__ == "__main__":
    main()
