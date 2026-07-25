"""Summarise the audit log — a tiny SOC-style view over tool activity.

    python scripts/analyze_audit.py [path-to-audit.log]

Reports: call volume, allow/deny split, top denial reasons (what's being blocked),
slowest calls, and most-used tools/metrics. Malformed lines are skipped so a
stray non-JSON line never breaks the report.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT_LOG = Path(__file__).resolve().parents[1] / "logs" / "audit.log"


def load(path: Path) -> list[dict]:
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # skip non-JSON noise
        if rec.get("event") == "tool_call":
            events.append(rec)
    return events


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    if not path.exists():
        raise SystemExit(f"No audit log at {path}. Run some tool calls first.")

    events = load(path)
    if not events:
        raise SystemExit(f"No tool_call events in {path}.")

    total = len(events)
    decisions = Counter(e["decision"] for e in events)
    denials = Counter(e.get("reason", "") for e in events if e["decision"] == "deny")
    tools = Counter(e.get("tool", "?") for e in events)
    metrics = Counter(
        (e.get("arguments") or {}).get("metric")
        for e in events
        if e.get("tool") == "query_metric" and (e.get("arguments") or {}).get("metric")
    )
    slowest = sorted(events, key=lambda e: e.get("latency_ms", 0), reverse=True)[:5]

    line = "=" * 64
    print(line)
    print(f"AUDIT SUMMARY  ({path})")
    print(line)
    print(f"  tool calls        : {total}")
    print(f"  allowed / denied  : {decisions.get('allow', 0)} / {decisions.get('deny', 0)}")

    print("\n  most-used tools:")
    for tool, n in tools.most_common():
        print(f"    {n:>4}  {tool}")

    if metrics:
        print("\n  most-queried metrics:")
        for metric, n in metrics.most_common(5):
            print(f"    {n:>4}  {metric}")

    if denials:
        print("\n  top denial reasons:")
        for reason, n in denials.most_common(5):
            print(f"    {n:>4}  {reason[:80]}")

    print("\n  slowest calls:")
    for e in slowest:
        print(f"    {e.get('latency_ms', 0):>7.2f} ms  {e.get('tool')}  ({e.get('decision')})")
    print(line)


if __name__ == "__main__":
    main()
