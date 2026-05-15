# STATUS - directory-submission skill

Built end-to-end on 2026-05-15. **Production ready** as of the same day: real
brand assets in place, full product profile filled in, 233-target merged queue
generated, 1-target dry-run passed. See `PRODUCTION_READY.md` for the exact
command, wall-clock estimate, and audit trail layout.

## Repos created and pushed

- Standalone skill: <https://github.com/ChocoData-com/directory-submission-skill>
  - Branch: `main`
  - Initial commit: `20ea84d Initial: directory-submission skill (80 targets, dry-run safe)`
- Mirrored into the monorepo as a 4th skill:
  - <https://github.com/ChocoData-com/amazon-scraper-api-skills/tree/main/directory-submission>
  - Commit: `4ba8be7 Add 4th skill: directory-submission`
  - Monorepo `README.md` updated with the new row.

## Files created (standalone repo)

```
directory-submission-skill/
  SKILL.md                          # Skill manifest + how-to
  README.md                         # Quick-start
  LICENSE                           # MIT (attributes backlink-pilot)
  STATUS.md                         # this file
  package.json                      # node deps: playwright, yaml; optional MCP backends
  .gitignore
  product-profile.example.yaml      # full schema, amazonscraperapi.com filled in
  filtered-targets.yaml             # 80 targets, grouped by category
  backlink-pilot-targets.yaml       # third-party reference, 259 entries
  submission_history.json           # generated, audit log
  adapters/
    _browser.js                     # multi-backend abstraction
    generic.js                      # accessibility-tree fallback
    devhunt.js                      # custom (GitHub OAuth)
    saashub.js                      # custom (email login, ported from backlink-pilot)
    stackshare.js                   # custom (email login)
    uneed.js                        # custom (Tally iframe)
  scripts/
    filter_targets.py               # produces filtered-targets.yaml
    submit_one.py                   # single-site submit; dry-run safe
    batch_submit.py                 # queue runner with pacing + dedup
    scout_form.py                   # probe new sites, write stub adapter
    verify_submission.py            # post-submission grep check
  assets/
    logo-256.png                    # placeholder (256x256 PNG, purple disk)
    og-1200x630.png                 # placeholder (1200x630 solid PNG)
  dry-run-output/                   # screenshots written here
```

## Filtered target count

Input: 259 entries in `backlink-pilot-targets.yaml`.
Output: **80 entries** in `filtered-targets.yaml`, grouped:

| Category       | Count |
|----------------|-------|
| ai_directory   | 48    |
| saas           | 25    |
| api            | 3     |
| dev_tools      | 2     |
| software       | 1     |
| startup        | 1     |
| **Total**      | **80** |

Filter rules (see `scripts/filter_targets.py`):

- Sections kept: `overseas_ai_directories`, `overseas_general`, `overseas_directories`, `awesome_lists`.
- Dropped: `chinese_*`, `reddit`, `communities_manual` (except a small whitelist).
- Dropped any entry with `status: dead` or `status: paid`.
- Dropped Chinese-only entries (`lang: zh`).
- Dropped manual-flow entries except a curated whitelist (DevHunt, Indie Hackers, Show HN, AlternativeTo, Betalist, MakerPeak, AITopTools).
- Dropped 29 generic PR/business directory names that backlink-pilot scraped but are irrelevant for a dev tool (ASR, 01webdirectory, etc.).
- Force-included the 10 manually-identified seed targets even if missing upstream.

## Dry-run test results

Ran `scripts/submit_one.py --dry-run` against the three required targets.
All three reached the page, took a screenshot, recorded a structured
report to `submission_history.json`, and exited cleanly without
submitting.

| Site         | Adapter      | Page reachable | Fields detected | Screenshot | Notes |
|--------------|--------------|----------------|-----------------|------------|-------|
| TheSaaSDir   | generic.js   | yes            | name + description + submit | `dry-run-output/TheSaaSDir-...png` (177 KB) | Generic accessibility-tree fallback works well; URL field not detected with the patterns we ship (form uses a non-standard label) |
| DevHunt      | devhunt.js   | yes (form page loaded) | 0 visible inputs at probe time | `dry-run-output/devhunt-...png` (102 KB) | DevHunt is a React SPA; the form is rendered after our 2s settle. For live submission, the user needs to be logged in via GitHub OAuth (the dry-run skips login by design) |
| apilist.fun  | generic.js   | yes (page loaded with 521 body) | 0 detected | `dry-run-output/apilist.fun-...png` (60 KB) | Site is currently down: Cloudflare returns HTTP 521 ("Web Server Is Down"). Our adapter still recorded the attempt and saved a screenshot. The filtered list should mark this entry `status: dead` if the outage persists |

All 3 entries are persisted in `submission_history.json`. Backend
auto-picked: `playwright-mcp` (because `@playwright/mcp` is installed in
`node_modules`). Plain `playwright` is the underlying engine.

## Outstanding for the user

1. ~~**Replace placeholder assets.**~~ DONE 2026-05-15. `assets/logo-256.png`
   is now a 256x256 brand-orange (#f90) PNG with white "ASA" wordmark;
   `assets/og-1200x630.png` is a production OG image with the Amazon
   Scraper API headline, tagline, URL, free-tier callout, and pricing badge.
   Both generated with Pillow from the live-site CSS color tokens.
2. **Edit `product-profile.yaml`.** Set the email address, Twitter
   handle, GitHub org, and any login creds you want the SaaSHub /
   StackShare / Uneed adapters to use.
3. **Install optional backends** for sites where the generic adapter
   misses fields:
   - `npm install @playwright/mcp` (recommended, already installed in this checkout).
   - `npm install @browserbasehq/stagehand` for LLM-driven fills on JS-heavy forms (DevHunt v2).
4. **First-time DevHunt login.** Run a one-shot interactive Chromium
   session to set the GitHub OAuth cookie, OR set
   `credentials.devhunt.github_token` in `product-profile.yaml`.
5. **Run the batch.** Once #1-#3 are done:
   ```bash
   # Sanity dry-run across all targets first
   python scripts/batch_submit.py --profile product-profile.yaml --dry-run

   # Then for real, high-priority first
   python scripts/batch_submit.py --profile product-profile.yaml --priority high
   ```
   With `pacing.min_interval_ms=60000` and 80 targets, the full queue
   takes ~80 minutes. Each entry is logged to `submission_history.json`.
6. **Tune low-detection sites.** Several `ai_directory` entries use
   unusual form widgets the generic adapter cannot read. Run
   `scripts/scout_form.py --url <site>/submit --name <Name>` to
   generate an adapter stub, then customise.

## Cost estimate

| Path                                      | Cost per submission | Full 80-target queue |
|-------------------------------------------|---------------------|----------------------|
| This skill (local Playwright)             | $0                  | **$0**               |
| Apify directory-submission actors         | ~$0.90              | ~$72                 |
| Manual VA at $15/hr, 30 min per site      | ~$7.50              | ~$600                |

Plus a future fixed cost: writing one custom adapter per site whose
generic-fallback miss rate is high. Typical: 30 minutes per adapter,
amortised across every future product profile you submit.
