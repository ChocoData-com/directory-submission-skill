# directory-submission

Automate listing a SaaS / dev tool / API on 80+ curated directories.
Single product profile, one command per site, full audit trail.

```bash
# Setup once
npm install && npx playwright install chromium
pip install pyyaml
cp product-profile.example.yaml product-profile.yaml
# edit product-profile.yaml with your product details

# Dry-run on one site (no submission, just probe + screenshot)
python scripts/submit_one.py --profile product-profile.yaml \
  --site "TheSaaSDir" --dry-run

# Submit for real
python scripts/submit_one.py --profile product-profile.yaml \
  --site "TheSaaSDir"

# Run the whole queue
python scripts/batch_submit.py --profile product-profile.yaml \
  --priority high
```

See [SKILL.md](./SKILL.md) for the full how-to, schema, and adapter
pattern.

## What you get

- `filtered-targets.yaml` — 80 directories that accept dev-tool / API /
  SaaS submissions, filtered from
  [s87343472/backlink-pilot](https://github.com/s87343472/backlink-pilot)'s
  259-entry source list. Live + English + auto-fillable only.
- `adapters/` — JS adapters for each site:
  - `generic.js` — accessibility-tree fallback, works for ~70% of forms.
  - `devhunt.js`, `saashub.js`, `stackshare.js`, `uneed.js` — custom flows
    for sites with login or multi-step forms.
- `scripts/` — Python orchestration:
  - `submit_one.py` — one site at a time, dry-run safe.
  - `batch_submit.py` — queue with pacing + history dedup.
  - `scout_form.py` — probe a new directory and generate an adapter stub.
  - `verify_submission.py` — post-submission grep for our listing.
- `submission_history.json` — append-only audit log.
- `dry-run-output/` — full-page screenshots per attempt.

## Why fork from backlink-pilot?

We did not want to maintain 259 unstable adapters. Backlink-pilot already
encodes which directories are alive, which want what fields, and ships a
good generic accessibility-tree fallback. We trimmed the list, added
multi-backend support (Playwright-MCP, Stagehand, Claude-in-Chrome) and
made dry-run a first-class flag.

## Browser backends

`BROWSER_BACKEND` env var (or `browser.backend` in the profile):

- `playwright` — direct, always works.
- `playwright-mcp` — same protocol, driven via `@playwright/mcp`.
- `stagehand` — LLM-driven actions for forms `generic.js` cannot read.
- `chrome-mcp` — drive the user's own Chrome via the Claude-in-Chrome
  extension. Useful for sites where you are already logged in.

Defaults to `auto`, which probes in priority order.

## Attribution

This project re-uses adapter patterns from
[s87343472/backlink-pilot](https://github.com/s87343472/backlink-pilot)
(MIT). The original 259-target `targets.yaml` is preserved as
`backlink-pilot-targets.yaml` for reference. Filter logic, Python
orchestration, multi-backend support, audit trail, and dry-run mode are
new to this repo.

## License

MIT. See [LICENSE](./LICENSE).
