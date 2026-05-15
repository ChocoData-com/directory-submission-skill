#!/usr/bin/env python3
"""
filter_targets.py

Read backlink-pilot's 259-entry targets.yaml, filter down to ~80 targets that
make sense for a dev-tool API product (amazonscraperapi.com is the seed
profile), and write the result to filtered-targets.yaml.

Filter rules:
  1. lang must be "en" or "multi" (drop "zh"-only entries)
  2. drop entries with status: dead, paid, or known-broken
  3. drop sections that need manual-only flow:
     - reddit
     - communities_manual (except a curated whitelist)
     - chinese_general / chinese_ai_directories
  4. keep auto: yes targets first, then a small handful of "manual" entries
     that are worth the human pass (DevHunt, IndieHackers, Show HN)
  5. always include the 10 manually-identified seed targets, even if they
     are not in backlink-pilot's list

Run:
  python scripts/filter_targets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "PyYAML is required. Install with: pip install pyyaml\n"
    )
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "backlink-pilot-targets.yaml"
OUT = REPO_ROOT / "filtered-targets.yaml"

# Sections that contain auto-fillable, English-friendly targets
KEEP_SECTIONS = {
    "overseas_ai_directories",
    "overseas_general",
    "overseas_directories",
    "awesome_lists",
}

# A small set of "manual" entries we still want to keep (worth the human pass)
MANUAL_WHITELIST = {
    "DevHunt",
    "Dev Hunt",
    "Indie Hackers",
    "Show HN (Hacker News)",
    "Product Hunt",
    "AlternativeTo",
    "Betalist",
    "MakerPeak",
    "Broadwise.org",
    "AITopTools",
}

# Manually-identified seed targets — must always appear in the output
SEED_TARGETS = [
    {
        "name": "DevHunt",
        "submit_url": "https://devhunt.org/",
        "type": "listing",
        "auto": "manual",
        "lang": "en",
        "notes": "Curated dev tool directory, GitHub OAuth login",
        "category": "dev_tools",
        "priority": "high",
    },
    {
        "name": "TheSaaSDir",
        "submit_url": "https://www.thesaasdir.com/submit",
        "type": "form",
        "auto": "yes",
        "lang": "en",
        "notes": "Free SaaS directory, dofollow",
        "category": "saas",
        "priority": "high",
    },
    {
        "name": "apilist.fun",
        "submit_url": "https://apilist.fun/submit",
        "type": "form",
        "auto": "yes",
        "lang": "en",
        "notes": "API directory, free listing",
        "category": "api",
        "priority": "high",
    },
    {
        "name": "StackShare",
        "submit_url": "https://stackshare.io/services/new",
        "type": "form",
        "auto": "manual",
        "lang": "en",
        "notes": "Requires account, tool/service catalog",
        "category": "dev_tools",
        "priority": "medium",
    },
    {
        "name": "Crozdesk",
        "submit_url": "https://crozdesk.com/submit-software",
        "type": "form",
        "auto": "yes",
        "lang": "en",
        "notes": "B2B software directory",
        "category": "saas",
        "priority": "medium",
    },
    {
        "name": "apivault.dev",
        "submit_url": "https://apivault.dev/submit",
        "type": "form",
        "auto": "yes",
        "lang": "en",
        "notes": "Public API directory",
        "category": "api",
        "priority": "high",
    },
    {
        "name": "apistack.io",
        "submit_url": "https://apistack.io/submit",
        "type": "form",
        "auto": "yes",
        "lang": "en",
        "notes": "API marketplace",
        "category": "api",
        "priority": "high",
    },
    {
        "name": "KillerStartups",
        "submit_url": "https://www.killerstartups.com/submit-startup/",
        "type": "form",
        "auto": "yes",
        "lang": "en",
        "notes": "Startup directory",
        "category": "startup",
        "priority": "medium",
    },
    {
        "name": "SaaSHub",
        "submit_url": "https://www.saashub.com/new",
        "type": "form",
        "auto": "manual",
        "lang": "en",
        "notes": "Major SaaS directory, requires email login",
        "category": "saas",
        "priority": "high",
        "adapter": "saashub",
    },
    {
        "name": "SourceForge",
        "submit_url": "https://sourceforge.net/software/vendors/new",
        "type": "form",
        "auto": "yes",
        "lang": "en",
        "notes": "20M monthly users",
        "category": "software",
        "priority": "high",
    },
]

# Names from backlink-pilot we want to drop because the form requires
# heavy account/captcha work or the niche is wrong (PR/business dirs)
EXTRA_DROP = {
    "ASR",
    "01webdirectory",
    "247WebDirectory",
    "9Sites.net",
    "ABC Directory",
    "All Business Directory",
    "All States USA Directory",
    "BusinessSeek.biz",
    "Submission Web Directory",
    "Highrankdirectory",
    "Sonic Run",
    "Site Promotion Directory",
    "SitesWebdirectory",
    "Marketing Internet Directory",
    "Promote Business Directory",
    "ProLinkDirectory",
    "GainWeb.org",
    "Jayde",
    "Free Directory",
    "Free PR Web Directory",
    "Free Internet Web Directory",
    "TXTLinks",
    "Tsection",
    "Thales Directory",
    "Quality Internet Directory",
    "UK Internet Directory",
    "USA Websites Directory",
    "World Web Directory",
    "Submit.biz",
}


def section_category(section: str) -> str:
    """Map a backlink-pilot section to our category enum."""
    if section == "overseas_ai_directories":
        return "ai_directory"
    if section == "overseas_general":
        return "saas"
    if section == "overseas_directories":
        return "web_directory"
    if section == "awesome_lists":
        return "github_awesome"
    return "other"


def normalize(entry: dict, section: str) -> dict:
    """Add category + priority + adapter hint fields."""
    name = entry.get("name", "").lower()
    out = {
        "name": entry["name"],
        "submit_url": entry["submit_url"],
        "type": entry.get("type", "form"),
        "auto": entry.get("auto", "yes"),
        "lang": entry.get("lang", "en"),
        "category": section_category(section),
    }
    if entry.get("notes"):
        out["notes"] = entry["notes"]
    # Priority heuristic — higher for known dev/api/saas-adjacent names
    priority = "low"
    keywords_high = ("api", "saashub", "alternativeto", "sourceforge",
                     "stackshare", "devhunt", "indiehack")
    keywords_med = ("hunt", "tool", "stack", "launch", "dev",
                    "tech", "startup", "indie")
    if any(k in name for k in keywords_high):
        priority = "high"
    elif any(k in name for k in keywords_med):
        priority = "medium"
    out["priority"] = priority
    return out


def main():
    if not SOURCE.exists():
        sys.stderr.write(f"ERROR: source file not found: {SOURCE}\n")
        sys.stderr.write(
            "Run from the repo root, and make sure backlink-pilot-targets.yaml "
            "is in place.\n"
        )
        sys.exit(1)

    with SOURCE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    filtered: list[dict] = []
    seen_urls: set[str] = set()

    # First pass: walk backlink-pilot sections
    for section, entries in (data or {}).items():
        if section not in KEEP_SECTIONS:
            continue
        for entry in entries or []:
            name = entry.get("name", "")
            url = entry.get("submit_url", "")
            if not url:
                continue
            # Skip duplicates by URL
            if url in seen_urls:
                continue
            # Status filters
            status = entry.get("status")
            if status in {"dead", "paid"}:
                continue
            # Language filter
            lang = entry.get("lang", "en")
            if lang == "zh":
                continue
            # Manual filter
            auto = entry.get("auto", "yes")
            if auto == "manual" and name not in MANUAL_WHITELIST:
                continue
            if auto == "no":
                continue
            # Explicit drops (web-directory bulk)
            if name in EXTRA_DROP:
                continue
            seen_urls.add(url)
            filtered.append(normalize(entry, section))

    # Second pass: prepend seeds (and de-dupe)
    seed_by_url: dict[str, dict] = {s["submit_url"]: s for s in SEED_TARGETS}
    merged: list[dict] = []
    seen_final: set[str] = set()
    for s in SEED_TARGETS:
        merged.append(s)
        seen_final.add(s["submit_url"])
    for entry in filtered:
        if entry["submit_url"] in seen_final:
            continue
        merged.append(entry)
        seen_final.add(entry["submit_url"])

    # Cap at 80 — keep all high/medium priority first
    high = [e for e in merged if e.get("priority") == "high"]
    med = [e for e in merged if e.get("priority") == "medium"]
    low = [e for e in merged if e.get("priority") == "low"]
    final = high + med + low
    final = final[:80]

    # Group by category for the output file
    by_cat: dict[str, list[dict]] = {}
    for e in final:
        cat = e.get("category", "other")
        by_cat.setdefault(cat, []).append(e)

    out = {
        "_meta": {
            "source": "Filtered from s87343472/backlink-pilot/targets.yaml",
            "filter_script": "scripts/filter_targets.py",
            "count": len(final),
            "by_category": {k: len(v) for k, v in by_cat.items()},
        },
    }
    out.update(by_cat)

    with OUT.open("w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True,
                       default_flow_style=False)

    print(f"Wrote {len(final)} targets to {OUT.name}")
    print("By category:")
    for k, v in by_cat.items():
        print(f"  {k}: {len(v)}")


if __name__ == "__main__":
    main()
