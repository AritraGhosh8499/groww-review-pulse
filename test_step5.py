"""Step 5 checks for MCP + approval workflow.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
NOTES_PATH = OUTPUTS_DIR / "notes_doc.md"
EMAIL_PATH = OUTPUTS_DIR / "email_draft.md"
LOG_PATH = OUTPUTS_DIR / "approval_log.jsonl"

BACKUP_DIR = BASE_DIR / ".step5_backup"


def backup_and_remove():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for name in ["notes_doc.md", "email_draft.md", "approval_log.jsonl"]:
        path = OUTPUTS_DIR / name
        if path.exists():
            shutil.copy2(path, BACKUP_DIR / name)
            os.remove(path)


def restore_backups():
    for name in ["notes_doc.md", "email_draft.md", "approval_log.jsonl"]:
        src = BACKUP_DIR / name
        if src.exists():
            dst = OUTPUTS_DIR / name
            shutil.copy2(src, dst)
    # Clean backup dir
    try:
        shutil.rmtree(BACKUP_DIR)
    except Exception:
        pass


def count_entry_headings(text: str) -> int:
    count = 0
    for line in text.splitlines():
        if line.strip().startswith("## Entry —"):
            count += 1
    return count


def run_workflow(input_text: str) -> str:
    result = subprocess.run(
        [sys.executable, "run_workflow.py"],
        cwd=str(BASE_DIR),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    # Combine stdout and stderr
    output = (result.stdout or "") + (result.stderr or "")
    return output


def main() -> int:
    print("=" * 72)
    print("STEP 5 TESTS - MCP + approval workflow")
    print("=" * 72)
    print()

    passed = 0
    total = 8

    # Backup and remove outputs
    backup_and_remove()

    try:
        # a) Approval blocks actions: run with "n\n"
        try:
            output = run_workflow("n\n")
            assert "Cancelled" in output, "Output does not contain 'Cancelled'"
            assert not NOTES_PATH.exists(), "notes_doc.md was created when it should not be"
            assert not EMAIL_PATH.exists(), "email_draft.md was created when it should not be"
            print("PASS  a) Approval blocks actions (n) - Cancelled, no files created")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  a) Approval blocks actions (n)\n      {exc}")
        except Exception as exc:
            print(f"FAIL  a) Approval blocks actions (n)\n      unexpected {type(exc).__name__}: {exc}")

        # b) Approval allows actions: run again with "y\n"
        try:
            output = run_workflow("y\n")
            assert NOTES_PATH.exists(), "notes_doc.md was not created"
            assert EMAIL_PATH.exists(), "email_draft.md was not created"
            print("PASS  b) Approval allows actions (y) - notes_doc.md and email_draft.md created")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  b) Approval allows actions (y)\n      {exc}")
        except Exception as exc:
            print(f"FAIL  b) Approval allows actions (y)\n      unexpected {type(exc).__name__}: {exc}")

        # c) notes_doc.md's json block contains all 6 keys
        try:
            notes_content = NOTES_PATH.read_text(encoding="utf-8")
            # Find the JSON payload block
            assert "```json" in notes_content, "No JSON block found in notes_doc.md"
            # Extract JSON
            start = notes_content.find("```json") + 7
            end = notes_content.find("```", start)
            json_str = notes_content[start:end].strip()
            payload = json.loads(json_str)
            required_keys = {"date", "top_themes", "weekly_pulse", "identified_fee_issue", "explanation_bullets", "source_links"}
            missing = required_keys - set(payload.keys())
            assert not missing, f"Missing keys: {missing}"
            print("PASS  c) notes_doc.md JSON block contains all 6 keys")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  c) notes_doc.md JSON block contains all 6 keys\n      {exc}")
        except Exception as exc:
            print(f"FAIL  c) notes_doc.md JSON block contains all 6 keys\n      unexpected {type(exc).__name__}: {exc}")

        # d) email_draft.md checks
        try:
            email_content = EMAIL_PATH.read_text(encoding="utf-8")
            assert email_content.startswith("To:") or "Subject:" in email_content.splitlines()[0] or "Subject:" in email_content, "Email format issue"
            # Check subject starts with specific text
            lines = email_content.splitlines()
            subject_line = None
            for l in lines:
                if l.lower().startswith("subject:"):
                    subject_line = l
                    break
            assert subject_line is not None, "No Subject line found"
            assert subject_line.strip().startswith("Subject: Weekly Product Pulse + Customer Clarification —"), f"Subject does not start correctly: {subject_line}"
            assert "NOT SENT" in email_content, "Email does not contain 'NOT SENT'"
            assert "Reusable support snippet (copy/paste)" in email_content, "Missing support snippet heading"
            print("PASS  d) email_draft.md has correct subject, contains NOT SENT and support snippet heading")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  d) email_draft.md checks\n      {exc}")
        except Exception as exc:
            print(f"FAIL  d) email_draft.md checks\n      unexpected {type(exc).__name__}: {exc}")

        # e) Append, not overwrite: run again with "y\n"
        try:
            output = run_workflow("y\n")
            notes_content = NOTES_PATH.read_text(encoding="utf-8")
            entry_count = count_entry_headings(notes_content)
            assert entry_count == 2, f"Expected 2 '## Entry —' headings, found {entry_count}"
            print(f"PASS  e) Append not overwrite - notes_doc.md now has {entry_count} '## Entry —' headings")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  e) Append not overwrite\n      {exc}")
        except Exception as exc:
            print(f"FAIL  e) Append not overwrite\n      unexpected {type(exc).__name__}: {exc}")

        # f) No sending code: mcp_server.py does not contain "smtplib" or "send_message"
        try:
            mcp_content = (BASE_DIR / "mcp_server.py").read_text(encoding="utf-8")
            assert "smtplib" not in mcp_content, "mcp_server.py contains 'smtplib'"
            assert "send_message" not in mcp_content, "mcp_server.py contains 'send_message'"
            print("PASS  f) No sending code in mcp_server.py")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  f) No sending code\n      {exc}")
        except Exception as exc:
            print(f"FAIL  f) No sending code\n      unexpected {type(exc).__name__}: {exc}")

        # g) Real MCP server: import mcp_server and use asyncio.run(mcp_server.mcp.list_tools())
        try:
            import mcp_server
            tools = asyncio.run(mcp_server.mcp.list_tools())
            tool_names = [t.name for t in tools]
            assert "append_to_doc" in tool_names, "append_to_doc tool not registered"
            assert "create_email_draft" in tool_names, "create_email_draft tool not registered"
            print(f"PASS  g) Real MCP server has tools: {', '.join(tool_names)}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  g) Real MCP server\n      {exc}")
        except Exception as exc:
            print(f"FAIL  g) Real MCP server\n      unexpected {type(exc).__name__}: {exc}")

        # h) approval_log.jsonl has one line per run (3 lines) with the answers n, y, y
        try:
            assert LOG_PATH.exists(), "approval_log.jsonl does not exist"
            with LOG_PATH.open("r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == 3, f"Expected 3 lines, found {len(lines)}"
            answers = []
            for l in lines:
                entry = json.loads(l)
                answers.append(entry.get("answer"))
            assert answers == ["n", "y", "y"], f"Expected answers ['n', 'y', 'y'], got {answers}"
            print(f"PASS  h) approval_log.jsonl has 3 lines with answers {answers}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  h) approval_log.jsonl checks\n      {exc}")
        except Exception as exc:
            print(f"FAIL  h) approval_log.jsonl checks\n      unexpected {type(exc).__name__}: {exc}")

    finally:
        # Restore backups at the end
        restore_backups()

    print()
    print("=" * 72)
    print(f"STEP 5 TESTS: {passed}/{total} passed")
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
