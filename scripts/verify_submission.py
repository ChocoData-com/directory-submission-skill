#!/usr/bin/env python3
"""
verify_submission.py

Post-submission check: visit the directory and look for our product's URL
or name to confirm the listing went live. Directories vary wildly in
turnaround (instant to "queued for manual review for 2 weeks"); this is a
best-effort probe.

Usage:
  python scripts/verify_submission.py \
    --profile product-profile.yaml \
    --site "TheSaaSDir"

Looks at submission_history.json for the latest entry for `site`, takes the
final_url (or falls back to the directory root), fetches it, and grep-scans
for the product name and URL.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML is required. pip install pyyaml\n")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY = REPO_ROOT / "submission_history.json"
FILTERED = REPO_ROOT / "filtered-targets.yaml"


def find_history_entry(site_name: str) -> dict | None:
    if not HISTORY.exists():
        return None
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    matches = [h for h in history if h.get("site") == site_name]
    return matches[-1] if matches else None


def find_filtered_entry(site_name: str) -> dict | None:
    if not FILTERED.exists():
        return None
    data = yaml.safe_load(FILTERED.read_text(encoding="utf-8")) or {}
    for key, entries in data.items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            if e.get("name", "").lower() == site_name.lower():
                return e
    return None


def fetch(url: str, timeout: float = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (verify-submission/1.0)",
            "Accept": "text/html,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(500_000).decode("utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--site", required=True)
    ap.add_argument("--probe-root", action="store_true",
                    help="also probe the directory's root + /search for the product name")
    args = ap.parse_args()

    profile = yaml.safe_load(Path(args.profile).read_text(encoding="utf-8"))
    product = (profile or {}).get("product") or {}
    name = product.get("name", "")
    url = product.get("url", "")
    if not name or not url:
        sys.stderr.write("profile missing product.name / product.url\n")
        sys.exit(2)

    domain = re.sub(r"^https?://", "", url).strip("/")
    history = find_history_entry(args.site)
    filtered = find_filtered_entry(args.site)

    candidate_urls = []
    if history and history.get("final_url"):
        candidate_urls.append(history["final_url"])
    if filtered and filtered.get("submit_url"):
        # Use the directory root as a fallback
        root = re.match(r"(https?://[^/]+)", filtered["submit_url"])
        if root and root.group(1) not in candidate_urls:
            candidate_urls.append(root.group(1))

    if not candidate_urls:
        sys.stderr.write(f"no candidate URLs found for site={args.site}\n")
        sys.exit(2)

    print(f"[verify] product={name} domain={domain}")
    found = False
    for u in candidate_urls:
        print(f"[verify] probing {u}")
        try:
            html = fetch(u)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            print(f"  ERROR: {e}")
            continue
        has_name = name.lower() in html.lower()
        has_domain = domain.lower() in html.lower()
        print(f"  has_name={has_name} has_domain={has_domain}")
        if has_name or has_domain:
            found = True
            break

    if found:
        print(f"[verify] OK — found a reference to {name} or {domain}")
        sys.exit(0)
    print("[verify] no reference found yet (still queued or not indexed)")
    sys.exit(1)


if __name__ == "__main__":
    main()
