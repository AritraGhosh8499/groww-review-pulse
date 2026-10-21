"""MCP server for the Groww product pulse workflow.

Two tools:
  - append_to_doc      : appends a dated entry to outputs/notes_doc.md
  - create_email_draft : writes a draft email to outputs/email_draft.md (never sends)

Run with:  python mcp_server.py
"""

from __future__ import annotations

import json
from pathlib import Path

try:  # official SDK, v1 name
    from mcp.server.fastmcp import FastMCP
except ImportError:  # mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

OUTPUTS_DIR = Path(__file__).parent / "outputs"
NOTES_PATH = OUTPUTS_DIR / "notes_doc.md"
EMAIL_PATH = OUTPUTS_DIR / "email_draft.md"
DOC_HEADER = "# Groww Product Pulse — Notes Doc"

mcp = FastMCP("groww-pulse")


@mcp.tool()
def append_to_doc(
    date: str,
    top_themes: list[str],
    weekly_pulse: str,
    identified_fee_issue: str,
    explanation_bullets: list[str],
    source_links: list[str],
) -> str:
    """Append a new entry to outputs/notes_doc.md (never overwrites existing content)."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "date": date,
        "top_themes": top_themes,
        "weekly_pulse": weekly_pulse,
        "identified_fee_issue": identified_fee_issue,
        "explanation_bullets": explanation_bullets,
        "source_links": source_links,
    }

    lines = []
    if not NOTES_PATH.exists():
        lines += [DOC_HEADER, ""]
    lines += [
        f"## Entry — {date}",
        "",
        "### Top themes",
        "",
    ]
    lines += [f"- {theme}" for theme in top_themes]
    lines += [
        "",
        "### Weekly pulse",
        "",
        weekly_pulse,
        "",
        "### Identified fee issue",
        "",
        identified_fee_issue,
        "",
        "### Explanation bullets",
        "",
    ]
    lines += [f"- {bullet}" for bullet in explanation_bullets]
    lines += [
        "",
        "### Source links",
        "",
    ]
    lines += [f"- {link}" for link in source_links]
    lines += [
        "",
        "### Payload",
        "",
        "```json",
        json.dumps(payload, indent=2, ensure_ascii=False),
        "```",
        "",
    ]

    with NOTES_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    return f"Appended entry for {date} to {NOTES_PATH}"


@mcp.tool()
def create_email_draft(subject: str, body: str, to: str = "product-team@example.com") -> str:
    """Save an email draft to outputs/email_draft.md. This tool only writes a local file and never sends email."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    text = "\n".join(
        [
            "To: " + to,
            "Subject: " + subject,
            "Status: DRAFT — NOT SENT",
            "",
            body,
            "",
        ]
    )
    EMAIL_PATH.write_text(text, encoding="utf-8")

    return f"Draft saved to {EMAIL_PATH} (not sent)"


if __name__ == "__main__":
    mcp.run()
