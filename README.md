# Groww Review Pulse

AI workflow that turns Groww Play Store reviews into a weekly product pulse and a fee explainer, then logs them via MCP after human approval.

## Flow

```
data/reviews.csv
      │
      ▼
analyze.py            themes, quotes, fee issue      → outputs/insights.json
      │
      ▼
generate.py           LLM pulse + fee explainer       → outputs/weekly_pulse.md
                                                      → outputs/fee_explainer.md
      │
      ▼
run_workflow.py       APPROVAL (y/n)                  → nothing runs unless you type y
      │
      ▼
mcp_server.py tools   append_to_doc, create_email_draft
      │
      ▼
outputs/notes_doc.md  +  outputs/email_draft.md
```

## How to run

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root (the key never goes into any other file):

```
GROQ_API_KEY=your_key
GROQ_MODEL=openai/gpt-oss-120b
```

Then:

```
python fetch_reviews.py
python run_workflow.py
```

`python fetch_reviews.py` is optional — `data/reviews.csv` is already included, so you can go straight to `python run_workflow.py`.

## Where the MCP approval happens

The gate is in `run_workflow.py`:

```python
answer = input("Approve these 2 actions? (y/n): ").strip().lower()
```

- Nothing is written to the notes doc or the email draft unless you type `y`.
- Typing `n` cancels the run: no MCP action is executed and nothing is saved to the doc or the email.
- Every decision, approved or cancelled, is appended to `outputs/approval_log.jsonl` with a timestamp, the answer and the actions that ran.
- The email is only a draft — `create_email_draft` writes `outputs/email_draft.md` and never sends mail.

## MCP tools

`mcp_server.py` is a FastMCP server (`mcp = FastMCP("groww-pulse")`) with two tools:

| Tool | What it does |
| --- | --- |
| `append_to_doc` | Appends a dated entry (top themes, pulse, fee issue, explanation bullets, source links, JSON payload) to `outputs/notes_doc.md`. It appends, it never overwrites. |
| `create_email_draft` | Writes the pulse plus the fee explainer as a reusable support snippet to `outputs/email_draft.md`, marked `DRAFT — NOT SENT`. |

The server can also run standalone: `python mcp_server.py`.

## Fee issue identified from the reviews

**Extra charges on top of brokerage (external + DP charges)** — mentioned in **40** reviews (`outputs/insights.json` → `fee_issue`).

Why this one: it is the most frequent charge-related confusion in the reviews. Users expect to pay only brokerage, then see extra DP and statutory charges on top and call them "hidden charges". The comparison in `analyze.py` scores this bucket (40) against the "brokerage rate too high" bucket (10), so the extra-charge wording wins by 4x.

Example snippets from the fee evidence in `outputs/insights.json`, copied exactly:

> Hidden charges on cancelled/unexecuted orders eat up most of your F&O profit.

> Direct mutual funds are available and no fees or other hidden charges are levied.

## Top 3 themes

| Theme | Reviews | Negative reviews | Trend |
| --- | --- | --- | --- |
| Customer support & withdrawals | 225 | 170 | rising |
| Charges & brokerage | 189 | 117 | stable |
| App glitches & order issues | 132 | 94 | stable |

## Use of AI

- The Groq LLM, with the model set by `GROQ_MODEL` (default `openai/gpt-oss-120b`), writes the wording of the weekly pulse: the one-line comment per theme, the key observation and the three action ideas.
- The model only sees a trimmed JSON payload of counts and trends. The user quotes and the fee facts are inserted straight from the review data and the official Groww sources (`sources.md`), so they cannot be invented. `analyze.py` asserts that every quote and fee snippet appears word-for-word in `data/reviews.csv`, and `test_step3.py` re-checks it.
- The fee explainer text is fixed text, not model output.
- If the LLM is unavailable (no key, no `groq` package, or the call fails) the workflow falls back to template text and still writes both files.

## Tests

```
python test_step3.py
python test_step4.py
python test_step5.py
```

- `test_step3.py` — checks `outputs/insights.json`: theme and top-theme counts, three quotes that exist verbatim in `data/reviews.csv`, the fee issue name/count, three verbatim fee snippets and the trend values.
- `test_step4.py` — checks `outputs/weekly_pulse.md` (length limit, required sections, exactly three action ideas, quotes verbatim, fee issue and count present) and `outputs/fee_explainer.md` (bullets, both source links, last-checked date). It also asserts `.env` is gitignored and that no API key appears in any `.md` file.
- `test_step5.py` — checks the approval gate and the MCP tools end to end: `n` writes nothing, `y` writes `notes_doc.md` and `email_draft.md`, the doc entry is appended and not overwritten, the email carries the right subject and `NOT SENT`, no sending code exists in `mcp_server.py`, and `outputs/approval_log.jsonl` records one line per run.

## Deliverables

| Deliverable | File |
| --- | --- |
| Reviews CSV | `data/reviews.csv` |
| Weekly pulse | `outputs/weekly_pulse.md` |
| Fee explainer | `outputs/fee_explainer.md` |
| Notes/Doc entry | `outputs/notes_doc.md` |
| Email draft | `outputs/email_draft.md` |
| Source list | `sources.md` |
| Screenshots | `screenshots/` |
| Demo video | (link coming) |

## Demo video

(link coming)
