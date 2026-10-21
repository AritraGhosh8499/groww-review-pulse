# Sources (last checked 2026-10-21)

## Links

- https://groww.in/pricing — official Groww charges (brokerage, DP charges, statutory charges, GST, auto square-off); used as the source for the fee explainer.
- https://groww.in/calculators/brokerage-calculator — official Groww calculator for the total charges on a trade; linked in the fee explainer.
- https://groww.in/regulatory-and-other-information — Groww's regulatory information page, used as the official reference for the regulatory context behind the charges listed in the fee explainer.
- https://play.google.com/store/apps/details?id=com.nextbillion.groww — the public Google Play listing the reviews were taken from.
- https://pypi.org/project/google-play-scraper/ — the library used to fetch the reviews (`fetch_reviews.py`).

## Review data

- App: Groww (`com.nextbillion.groww`), Google Play, lang `en`, country `in`.
- Reviews analysed: **1830** (from `outputs/insights.json` → `total_reviews`).
- Date range: **2026-07-29 to 2026-10-20** (from `outputs/insights.json` → `date_range`).
- The review rows live in `data/reviews.csv`; the counts and date range above are the ones recorded by `analyze.py` in `outputs/insights.json`.
