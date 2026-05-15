#!/usr/bin/env python3
"""
submit_one.py

Submit a product to ONE directory site by invoking the right JS adapter via
Node. Returns a structured report and updates submission_history.json.

Usage:
  python scripts/submit_one.py \
    --profile product-profile.yaml \
    --site "TheSaaSDir" \
    --target "https://www.thesaasdir.com/submit" \
    --dry-run

  python scripts/submit_one.py \
    --profile product-profile.yaml \
    --site "DevHunt" \
    --dry-run

If --target is omitted, the script looks up the site in filtered-targets.yaml
to find its submit_url and adapter hint.

Adapter routing:
  1. If the target entry has an `adapter` field, use adapters/<adapter>.js
  2. If a file adapters/<lower(name).js> exists, use it
  3. Otherwise use adapters/generic.js
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML is required. pip install pyyaml\n")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTERS_DIR = REPO_ROOT / "adapters"
HISTORY = REPO_ROOT / "submission_history.json"
FILTERED = REPO_ROOT / "filtered-targets.yaml"
QUEUE = REPO_ROOT / "queue.yaml"

REPORT_START = "---REPORT-JSON---"
REPORT_END = "---END-REPORT-JSON---"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _iter_entries(data: dict):
    """Yield entries from either the new queue.yaml schema (flat `targets:` list)
    or the legacy filtered-targets.yaml schema (category-keyed lists)."""
    if isinstance(data.get("targets"), list):
        yield from data["targets"]
        return
    for key, entries in data.items():
        if key in ("_meta", "metadata") or not isinstance(entries, list):
            continue
        yield from entries


def find_target(site_name: str) -> dict | None:
    needle = (site_name or "").lower().strip()
    for src in (QUEUE, FILTERED):
        if not src.exists():
            continue
        with src.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for entry in _iter_entries(data):
            name = (entry.get("name") or "").lower()
            domain = (entry.get("domain") or "").lower()
            if name == needle or domain == needle:
                return entry
    return None


def pick_adapter(site_entry: dict | None, site_name: str) -> Path:
    if site_entry and site_entry.get("adapter"):
        candidate = ADAPTERS_DIR / f"{site_entry['adapter']}.js"
        if candidate.exists():
            return candidate
    slug = slugify(site_name)
    by_slug = ADAPTERS_DIR / f"{slug}.js"
    if by_slug.exists():
        return by_slug
    return ADAPTERS_DIR / "generic.js"


def load_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def append_history(entry: dict) -> None:
    history = load_history()
    history.append(entry)
    HISTORY.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_adapter(adapter: Path, args: list[str]) -> tuple[int, str, dict | None]:
    cmd = ["node", str(adapter), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    out = proc.stdout + "\n" + proc.stderr
    report = None
    if REPORT_START in proc.stdout and REPORT_END in proc.stdout:
        try:
            chunk = proc.stdout.split(REPORT_START, 1)[1].split(REPORT_END, 1)[0]
            report = json.loads(chunk.strip())
        except (json.JSONDecodeError, IndexError):
            report = None
    return proc.returncode, out, report


def main():
    ap = argparse.ArgumentParser(description="Submit product to one directory")
    ap.add_argument("--profile", required=True, help="path to product-profile.yaml")
    ap.add_argument("--site", required=True, help="site name (matches filtered-targets.yaml)")
    ap.add_argument("--target", help="override submit_url for this run")
    ap.add_argument("--backend", help="browser backend (auto|playwright|playwright-mcp|stagehand|chrome-mcp)")
    ap.add_argument("--dry-run", action="store_true", help="probe form but do not submit")
    args = ap.parse_args()

    profile_path = Path(args.profile).resolve()
    if not profile_path.exists():
        sys.stderr.write(f"profile not found: {profile_path}\n")
        sys.exit(2)

    entry = find_target(args.site)
    target_url = args.target or (entry or {}).get("submit_url")
    if not target_url:
        sys.stderr.write(
            f"Site '{args.site}' not found in filtered-targets.yaml and no "
            f"--target override provided\n"
        )
        sys.exit(2)

    adapter = pick_adapter(entry, args.site)
    print(f"[submit_one] site={args.site} target={target_url} adapter={adapter.name}")

    cli_args = [
        "--profile", str(profile_path),
        "--site-name", args.site,
        "--target", target_url,
    ]
    if args.backend:
        cli_args += ["--backend", args.backend]
    if args.dry_run:
        cli_args.append("--dry-run")

    code, output, report = run_adapter(adapter, cli_args)
    if not report:
        # Synthesize a failure report so history stays consistent
        report = {
            "site": args.site,
            "target_url": target_url,
            "adapter": adapter.name,
            "dry_run": args.dry_run,
            "submitted": False,
            "error": "adapter did not emit a report (exit code %d)" % code,
            "raw_output_tail": output[-2000:],
        }
    report["adapter"] = adapter.name
    report["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    append_history(report)
    print(f"[submit_one] recorded -> {HISTORY.name}")
    print(json.dumps(report, indent=2)[:1500])
    sys.exit(0 if code == 0 else 1)


if __name__ == "__main__":
    main()
