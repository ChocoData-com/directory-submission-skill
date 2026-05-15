#!/usr/bin/env python3
"""
build_queue.py

Merge _backlink-research/validated-targets.yaml (rich schema) with the
backlink-pilot derived filtered-targets.yaml (legacy schema) into a single
queue.yaml ready for batch_submit.py.

- Dedupe by domain (case-insensitive).
- When both sources have the same domain, the validated entry wins.
- Assign priority high/medium/low per the spec.
- Map known domains to custom adapters; everything else uses generic.

Usage:
  python scripts/build_queue.py
"""
from __future__ import annotations
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML is required. pip install pyyaml\n")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAAS_FACTORY = REPO_ROOT.parent / "saas-factory"
VALIDATED = SAAS_FACTORY / "_backlink-research" / "validated-targets.yaml"
FILTERED = REPO_ROOT / "filtered-targets.yaml"
OUTPUT = REPO_ROOT / "queue.yaml"

# Adapter mapping
ADAPTER_BY_DOMAIN = {
    "devhunt.org": "devhunt",
    "saashub.com": "saashub",
    "stackshare.io": "stackshare",
    "uneed.best": "uneed",
}


def extract_domain(url_or_domain: str) -> str:
    s = (url_or_domain or "").strip()
    if not s:
        return ""
    if "://" not in s:
        s = "http://" + s
    try:
        host = urlparse(s).netloc.lower()
    except Exception:
        return s.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def name_from_domain(domain: str) -> str:
    # "supply.carrd.co" -> "Supply Carrd Co"
    core = domain.replace("www.", "")
    parts = re.split(r"[.\-_/]", core)
    parts = [p for p in parts if p]
    return " ".join(p.capitalize() for p in parts) if parts else domain


def adapter_for(domain: str) -> str:
    domain = (domain or "").lower()
    for needle, name in ADAPTER_BY_DOMAIN.items():
        if needle in domain:
            return name
    return "generic"


def derive_priority(rel_score, form_complexity, auth_required):
    rs = rel_score or 0
    fc = (form_complexity or "").lower()
    auth = bool(auth_required)
    if rs >= 4 and fc == "low" and not auth:
        return "high"
    if rs >= 3 and fc != "high":
        return "medium"
    return "low"


def derive_filtered_priority(entry):
    """For filtered-targets entries, normalize to high|medium|low based on the
    existing 'priority' field plus a few hints. Some entries have 'auto: manual'
    which means a form exists but probably needs login; we never call those high."""
    p = (entry.get("priority") or "medium").lower()
    auto = entry.get("auto")
    if isinstance(auto, str) and auto.lower() == "manual":
        if p == "high":
            p = "medium"
    if p not in ("high", "medium", "low"):
        p = "medium"
    return p


def map_filtered_to_target(entry):
    """Turn a filtered-targets entry into the unified queue schema."""
    submit_url = entry.get("submit_url") or ""
    domain = extract_domain(submit_url)
    priority = derive_filtered_priority(entry)
    return {
        "name": entry.get("name") or name_from_domain(domain),
        "domain": domain,
        "url": f"https://{domain}/" if domain else submit_url,
        "submit_url": submit_url,
        "category": entry.get("category") or "saas",
        "dr": None,
        "monthly_traffic_est": None,
        "form_complexity": "unknown",
        "auth_required": (str(entry.get("auto", "")).lower() == "manual"),
        "likely_dofollow": "unknown",
        "relevance_score": None,
        "priority": priority,
        "adapter": adapter_for(domain),
        "source": "filtered",
        "notes": entry.get("notes") or "",
    }


def map_validated_to_target(entry):
    """Turn a validated-targets entry into the unified queue schema."""
    submit_url = entry.get("submit_url") or entry.get("url") or ""
    domain = (entry.get("domain") or extract_domain(submit_url)).lower()
    # Cleanup category to be human-friendly
    category = entry.get("category") or "saas"
    priority = derive_priority(
        entry.get("relevance_score"),
        entry.get("form_complexity"),
        entry.get("auth_required"),
    )
    notes = entry.get("notes") or ""
    return {
        "name": name_from_domain(domain),
        "domain": domain,
        "url": entry.get("url") or f"https://{domain}/",
        "submit_url": submit_url,
        "category": category,
        "dr": entry.get("dr"),
        "monthly_traffic_est": entry.get("monthly_traffic_est"),
        "form_complexity": entry.get("form_complexity") or "unknown",
        "auth_required": bool(entry.get("auth_required")),
        "likely_dofollow": entry.get("likely_dofollow") or "unknown",
        "relevance_score": entry.get("relevance_score"),
        "priority": priority,
        "adapter": adapter_for(domain),
        "source": "validated",
        "notes": notes,
    }


def sort_key(t):
    # priority: high(0) before medium(1) before low(2)
    pri = {"high": 0, "medium": 1, "low": 2}.get(t.get("priority", "low"), 3)
    dr = -(t.get("dr") or 0)  # higher DR first
    fc_rank = {"low": 0, "medium": 1, "high": 2, "unknown": 3}.get(
        (t.get("form_complexity") or "unknown").lower(), 4
    )
    return (pri, dr, fc_rank, t.get("domain", ""))


def main():
    validated_count = 0
    filtered_count = 0
    domains_seen = {}  # domain -> entry

    # 1. Load validated first (they win on conflict).
    if VALIDATED.exists():
        with VALIDATED.open("r", encoding="utf-8") as f:
            vdata = yaml.safe_load(f) or {}
        vlist = vdata.get("validated") or []
        validated_count = len(vlist)
        for entry in vlist:
            mapped = map_validated_to_target(entry)
            d = mapped["domain"]
            if not d:
                continue
            domains_seen[d] = mapped
    else:
        sys.stderr.write(f"WARN: validated targets not found at {VALIDATED}\n")

    # 2. Add filtered entries only if their domain isn't already covered.
    if FILTERED.exists():
        with FILTERED.open("r", encoding="utf-8") as f:
            fdata = yaml.safe_load(f) or {}
        for k, entries in fdata.items():
            if k == "_meta" or not isinstance(entries, list):
                continue
            for entry in entries:
                filtered_count += 1
                mapped = map_filtered_to_target(entry)
                d = mapped["domain"]
                if not d:
                    continue
                if d not in domains_seen:
                    domains_seen[d] = mapped

    targets = sorted(domains_seen.values(), key=sort_key)

    # Priority breakdown
    pb = {"high": 0, "medium": 0, "low": 0}
    for t in targets:
        p = t.get("priority") or "low"
        pb[p] = pb.get(p, 0) + 1

    out = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total": len(targets),
            "sources": {
                "validated_targets": validated_count,
                "filtered_targets": filtered_count,
                "deduplicated": (validated_count + filtered_count) - len(targets),
            },
            "priority_breakdown": pb,
            "schema": "v1",
            "notes": (
                "Sorted: priority desc, DR desc, form_complexity asc. Each entry "
                "carries both `domain` (canonical) and `name` (human-readable) so "
                "the existing batch_submit.py / submit_one.py keep working."
            ),
        },
        "targets": targets,
    }

    with OUTPUT.open("w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=120)

    print(f"WROTE {OUTPUT}: {len(targets)} targets")
    print(f"  validated input: {validated_count}")
    print(f"  filtered input:  {filtered_count}")
    print(f"  deduplicated:    {(validated_count + filtered_count) - len(targets)}")
    print(f"  priority: {pb}")


if __name__ == "__main__":
    main()
