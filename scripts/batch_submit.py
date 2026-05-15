#!/usr/bin/env python3
"""
batch_submit.py

Iterate through filtered-targets.yaml and submit to each one, respecting
pacing settings and skipping anything already in submission_history.json.

Usage:
  python scripts/batch_submit.py --profile product-profile.yaml --dry-run
  python scripts/batch_submit.py --profile product-profile.yaml --limit 5
  python scripts/batch_submit.py --profile product-profile.yaml \
    --priority high --category api

Concurrency: serial by design. Directories don't like burst traffic and we
need to be polite. Pacing comes from the product profile's `pacing` block.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML is required. pip install pyyaml\n")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
FILTERED = REPO_ROOT / "filtered-targets.yaml"
HISTORY = REPO_ROOT / "submission_history.json"
SUBMIT_ONE = REPO_ROOT / "scripts" / "submit_one.py"


def load_targets(priority_filter=None, category_filter=None):
    if not FILTERED.exists():
        sys.stderr.write("filtered-targets.yaml missing — run scripts/filter_targets.py first\n")
        sys.exit(2)
    with FILTERED.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    targets = []
    for key, entries in data.items():
        if key == "_meta" or not isinstance(entries, list):
            continue
        for entry in entries:
            if priority_filter and entry.get("priority") != priority_filter:
                continue
            if category_filter and entry.get("category") != category_filter:
                continue
            targets.append(entry)
    return targets


def already_submitted(history: list[dict], name: str) -> bool:
    for h in history:
        if h.get("site") == name and h.get("submitted") and not h.get("dry_run"):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="max sites this run")
    ap.add_argument("--priority", choices=["high", "medium", "low"], default=None)
    ap.add_argument("--category", default=None)
    ap.add_argument("--backend", default=None)
    ap.add_argument("--skip-existing", action="store_true", default=True)
    args = ap.parse_args()

    with Path(args.profile).open("r", encoding="utf-8") as f:
        profile = yaml.safe_load(f) or {}
    pacing = profile.get("pacing") or {}
    min_interval = (pacing.get("min_interval_ms") or 60000) / 1000.0
    jitter = (pacing.get("jitter_ms") or 15000) / 1000.0

    history = []
    if HISTORY.exists():
        try:
            history = json.loads(HISTORY.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []

    targets = load_targets(args.priority, args.category)
    if args.skip_existing and not args.dry_run:
        targets = [t for t in targets if not already_submitted(history, t["name"])]
    if args.limit:
        targets = targets[: args.limit]

    print(f"[batch] running {len(targets)} target(s), dry_run={args.dry_run}")
    summary = {"ok": 0, "failed": 0, "items": []}
    for i, t in enumerate(targets, 1):
        print(f"\n=== [{i}/{len(targets)}] {t['name']} ===")
        cmd = [
            sys.executable, str(SUBMIT_ONE),
            "--profile", args.profile,
            "--site", t["name"],
            "--target", t["submit_url"],
        ]
        if args.backend:
            cmd += ["--backend", args.backend]
        if args.dry_run:
            cmd.append("--dry-run")
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
        ok = proc.returncode == 0
        summary["ok" if ok else "failed"] += 1
        summary["items"].append({
            "site": t["name"], "ok": ok, "exit": proc.returncode,
        })
        if i < len(targets):
            wait = max(0, min_interval + random.uniform(-jitter, jitter))
            print(f"[batch] sleeping {wait:.0f}s ...")
            time.sleep(wait)

    print("\n=== Batch summary ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
