"""Main workflow: analyse reviews, build the pulse and explainer, then (after
approval) run the two MCP-style actions.

Run with:  python run_workflow.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

from analyze import run_analysis
from generate import make_outputs
from mcp_server import append_to_doc, create_email_draft

BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
PULSE_PATH = OUTPUTS_DIR / "weekly_pulse.md"
EXPLAINER_PATH = OUTPUTS_DIR / "fee_explainer.md"
LOG_PATH = OUTPUTS_DIR / "approval_log.jsonl"


def log_decision(answer: str, actions: list[str]) -> None:
    """Append one JSON line recording the approval decision."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "answer": answer,
        "actions_run": actions,
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    today = date.today().isoformat()

    # ---------------------------------------------------------------- STEP 1
    print("STEP 1 — Review intelligence")
    insights = run_analysis()

    print("\nTop 3 themes")
    for index, name in enumerate(insights.get("top_themes", [])[:3], start=1):
        print(f"  {index}. {name}")

    fee = insights.get("fee_issue", {})
    print(f"\nFee issue : {fee.get('name', '?')}")
    print(f"Count     : {fee.get('count', 0)}")

    # ---------------------------------------------------------------- STEP 2/3
    print("\nSTEP 2/3 — Weekly pulse + fee explainer")
    outputs = make_outputs(insights)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    PULSE_PATH.write_text(outputs["weekly_pulse"], encoding="utf-8")
    EXPLAINER_PATH.write_text(outputs["fee_explainer"], encoding="utf-8")

    words = len(outputs["weekly_pulse"].split())
    print(f"Wrote {PULSE_PATH} ({words} words)")
    print(f"Wrote {EXPLAINER_PATH}")
    print(f"LLM used: {outputs['llm_used']}")

    # ---------------------------------------------------------------- email
    subject = f"Weekly Product Pulse + Customer Clarification — {today}"
    body = "\n".join(
        [
            outputs["weekly_pulse"],
            "",
            "----- Reusable support snippet (copy/paste) -----",
            "",
            outputs["fee_explainer"],
        ]
    )

    # ------------------------------------------------------------- approval
    top_themes = insights.get("top_themes", [])[:3]
    bullets = outputs["bullets"]
    links = outputs["source_links"]

    print()
    print("+" + "-" * 62 + "+")
    print("| MCP ACTIONS WAITING FOR YOUR APPROVAL" + " " * 24 + "|")
    print("+" + "-" * 62 + "+")
    print("  1. append_to_doc → outputs/notes_doc.md")
    print(f"       date      : {today}")
    print(f"       top themes: {', '.join(top_themes)}")
    print(f"       fee issue : {fee.get('name', '?')}")
    print(f"       bullets   : {len(bullets)}   links: {len(links)}")
    print("  2. create_email_draft → outputs/email_draft.md")
    print(f"       subject   : {subject}")
    print("       draft only — will NOT be sent")
    print("+" + "-" * 62 + "+")

    answer = input("Approve these 2 actions? (y/n): ").strip().lower()

    if answer != "y":
        print("Cancelled. No MCP actions were run. Nothing was saved to the doc or email.")
        log_decision(answer, [])
        return

    # -------------------------------------------------------------- actions
    doc_result = append_to_doc(
        date=today,
        top_themes=top_themes,
        weekly_pulse=outputs["weekly_pulse"],
        identified_fee_issue=fee.get("name", ""),
        explanation_bullets=bullets,
        source_links=links,
    )
    print(doc_result)

    email_result = create_email_draft(subject=subject, body=body)
    print(email_result)

    log_decision(answer, ["append_to_doc", "create_email_draft"])

    print("Done. Email was NOT sent — it is saved as a draft.")


if __name__ == "__main__":
    main()
