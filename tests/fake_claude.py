#!/usr/bin/env python3
"""Stand-in for the `claude` CLI in tests. Behaviour is chosen by FAKE_CLAUDE_MODE; argv is recorded."""
import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
rec = os.environ.get("FAKE_CLAUDE_ARGV")
if rec:
    with open(rec, "a") as f:
        f.write(json.dumps({"cwd": os.getcwd(), "argv": args}) + "\n")

if "--json-schema" in args:  # required_inputs
    if mode == "inputs-error":
        print(json.dumps({"is_error": True, "subtype": "error_during_execution", "result": "boom"})); sys.exit(1)
    if mode == "inputs-garbage":
        print("not json"); sys.exit(0)
    print(json.dumps({"is_error": False, "subtype": "success", "structured_output": {
        "suggested": {"app_name": "Invoice Hub", "must_have": "Create invoice\nSend PDF", "data_storage": "SQLite",
                      "auth": "NOT AN OPTION", "acceptance": "Given an invoice, when saved, then it is listed",
                      "evil_field": "x"},
        "questions": [
            {"id": "Currency", "label": "Default currency", "type": "select", "options": ["INR", "USD"], "default": "INR"},
            {"id": "stripe_api_key", "label": "Stripe API key", "type": "text", "default": ""},
            {"id": "tax_rate", "label": "Tax rate %", "type": "number", "default": "18"},
            {"id": "currency", "label": "dup", "type": "text", "default": ""},
            {"id": "pdf_logo", "label": "Logo on PDF", "type": "boolean", "default": "yes"},
            {"id": "server_port", "label": "Port", "type": "number", "default": "8765"},
            {"id": "report_format", "label": "Report format", "type": "text", "default": "pdf"},
            {"id": "bad", "label": "bad type", "type": "file", "default": ""},
            {"id": "tone", "label": "Tone", "type": "select", "options": [], "default": "x"}]}}))
    sys.exit(0)

def emit(o):
    print(json.dumps(o), flush=True)

emit({"type": "system", "subtype": "init"})
if mode == "slow":
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "working slowly"}]}})
    time.sleep(60)
if mode == "crash":
    print("Traceback: something broke", flush=True); sys.exit(3)
emit({"type": "assistant", "message": {"content": [
    {"type": "text", "text": "Reading BUILD_SPEC.md"},
    {"type": "tool_use", "name": "Write", "input": {"file_path": "app.py"}},
    {"type": "tool_use", "name": "TodoWrite", "input": {"todos": [{"status": "completed"}, {"status": "pending"}]}}]}})
emit({"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "Permission denied: rm"}]}})
Path("app.py").write_text("print('hi')\n")
Path("run.sh").write_text("#!/bin/sh\nsleep 1\n")
Path("docs").mkdir(exist_ok=True)
Path("docs/COMPLETION_REPORT.md").write_text("## Delivery summary\n- Outcome: built\n")
Path("docs/REUSE.md").write_text("reused things\n")
if any("ENHANCING an existing" in a for a in args):
    Path("docs/ENHANCE_REPORT.md").write_text("## Delivery summary\n- Outcome: enhanced\n")
if mode == "fail":
    emit({"type": "result", "subtype": "error_max_budget_usd", "is_error": True, "total_cost_usd": 5.01, "num_turns": 9})
    sys.exit(1)
emit({"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 1.23, "num_turns": 7,
      "result": "Built Invoice Hub", "permission_denials": [{"tool_name": "Bash"}]})
