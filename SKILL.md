---
name: directory-submission
description: "Submit a product to SaaS, dev-tool, and AI directories by filling submission forms via Playwright. Single product profile, reused across 80+ curated targets. Custom adapters plus a generic accessibility-tree fallback."
metadata:
  chocodata:
    emoji: "outbox"
    requires:
      env:
        - GITHUB_TOKEN
      node: ">=18"
      python: ">=3.9"
      playwright: true
allowed-tools: ["bash"]
---

# directory-submission

A skill that automates listing a product on 80+ SaaS, dev-tool, and AI
directories. It reads ONE product profile YAML, filters a curated target
list, and runs Playwright (or Playwright-MCP / Stagehand) to fill the
submission form for each directory.

Forked logic + adapter patterns from
[s87343472/backlink-pilot](https://github.com/s87343472/backlink-pilot)
(MIT). Curated target list, dry-run safety, multi-backend support, and
audit trail are new.

## When to use this skill

Trigger phrases:

- "submit us to [directory name]"
- "list amazonscraperapi on X"
- "fill the submission form at [URL]"
- "run the directory submission queue"
- "scout this submit page"
- "verify our listing on [directory]"

Do not use this skill for:

- Reddit posts, HackerNews, IndieHackers manual posts. Those need genuine
  engagement and are deliberately left out of the filtered list.
- Anything requiring CAPTCHA-solving without a human. The skill detects
  these and aborts.

## Setup

```bash
# 1. Install JS deps (Playwright + YAML)
npm install

# 2. Install browser binaries (one-time)
npx playwright install chromium

# 3. Install Python deps (YAML)
pip install pyyaml

# 4. Copy and edit the product profile
cp product-profile.example.yaml product-profile.yaml
# ...fill in your product details, ESPECIALLY product.url, name, description

# 5. Optional: install MCP backends
npm install @playwright/mcp           # default if you want MCP-driven flows
npm install @browserbasehq/stagehand  # LLM-driven actions for tricky forms
```

Required env (only for sites with GitHub OAuth login):

```bash
export GITHUB_TOKEN=ghp_...   # only DevHunt currently uses this
```

## Product profile schema

Every script reads `product-profile.yaml` (or whatever you pass via
`--profile`). The schema is documented inline in
`product-profile.example.yaml`. The fields the generic adapter expects:

```yaml
product:
  name: "..."                    # the brand name as listed
  tagline: "..."                 # 60-80 chars, used on every "tagline" slot
  short_description: "..."       # 160 chars, SEO meta description range
  long_description: |            # 500-1500 chars, "describe your tool" slot
    ...
  url: "https://..."             # the canonical product URL
  utm_url: "https://...?utm_..." # optional UTM-tagged variant
  pricing: "freemium"            # free | freemium | paid | open_source
  categories: [api, developer-tools, ecommerce]
  tags: [...]
  email: "hello@..."
  twitter: "handle"
  github: "org-or-user"
  logo_path: "assets/logo-256.png"
  og_image_path: "assets/og-1200x630.png"

credentials:
  saashub: { email: "...", password: "..." }
  stackshare: { email: "...", password: "..." }
  devhunt: { github_token: "${GITHUB_TOKEN}" }

browser:
  backend: "auto"   # auto | playwright | playwright-mcp | stagehand | chrome-mcp
  headless: true
  screenshot_dir: "./dry-run-output"

pacing:
  min_interval_ms: 60000
  same_site_interval_ms: 3600000
  jitter_ms: 15000
```

## Submission flow

1. `scripts/filter_targets.py` reduces the upstream 259-entry list to ~80
   targets relevant to dev-tool / API / SaaS niches. Output:
   `filtered-targets.yaml`.
2. `scripts/submit_one.py` submits to ONE site. Picks the right adapter
   (custom `adapters/<slug>.js` if it exists, otherwise `generic.js`).
   Appends a structured entry to `submission_history.json`.
3. `scripts/batch_submit.py` walks `filtered-targets.yaml`, calling
   `submit_one.py` for each entry, respecting `pacing.min_interval_ms`.
   Skips entries already marked submitted in history (unless `--dry-run`).
4. `scripts/scout_form.py` probes a new directory and auto-generates an
   adapter stub at `adapters/<slug>.js`.
5. `scripts/verify_submission.py` fetches the directory and grep-scans
   for our product name / domain to confirm the listing went live.

### Common commands

```bash
# Probe ONE site without submitting (safe)
python scripts/submit_one.py \
  --profile product-profile.yaml \
  --site "TheSaaSDir" \
  --dry-run

# Submit to ONE site for real
python scripts/submit_one.py \
  --profile product-profile.yaml \
  --site "TheSaaSDir"

# Dry-run the entire queue (no actual submissions)
python scripts/batch_submit.py \
  --profile product-profile.yaml \
  --dry-run

# Run the queue, limit to 5 high-priority sites
python scripts/batch_submit.py \
  --profile product-profile.yaml \
  --priority high \
  --limit 5

# Scout a directory we have not seen before
python scripts/scout_form.py \
  --url "https://newdir.example/submit" \
  --name "NewDir" \
  --profile product-profile.yaml

# Verify a listing went live
python scripts/verify_submission.py \
  --profile product-profile.yaml \
  --site "TheSaaSDir"
```

## Custom adapter pattern

When `generic.js` cannot fill a form (multi-step wizard, custom widgets,
login required, captcha), drop a custom adapter into `adapters/<slug>.js`.
Pattern:

```javascript
import { readFileSync } from "node:fs";
import yaml from "yaml";
import { launchPage, pickBackend, jitterDelay } from "./_browser.js";

export async function run(opts) {
  const cfg = yaml.parse(readFileSync(opts.profile, "utf-8"));
  const backend = await pickBackend(opts.backend);
  const { page, close } = await launchPage({ backend, headless: true });

  try {
    await page.goto(opts.target);
    // ...site-specific fill + click logic...
    const report = { site: "...", submitted: !opts.dryRun, ... };
    console.log("---REPORT-JSON---");
    console.log(JSON.stringify(report, null, 2));
    console.log("---END-REPORT-JSON---");
  } finally {
    await close();
  }
}
```

The Python orchestrator picks up the JSON block between the markers and
appends it to `submission_history.json`. Always emit a report, even on
failure.

## Pitfalls

- **Anti-bot blocking.** Every adapter sets a realistic user-agent and
  human-ish delays via `jitterDelay`. Stagehand and Playwright-MCP add
  more realism. If a site keeps blocking, switch to `BROWSER_BACKEND=chrome-mcp`
  to drive the user's real Chrome (with their cookies and history).
- **Double submissions.** `batch_submit.py` skips anything already in
  history as `submitted: true && dry_run: false`. To force a resubmission,
  delete the relevant entry from `submission_history.json` first.
- **Captcha.** If a page surfaces hCaptcha / reCAPTCHA / Turnstile, the
  adapter records the failure with `error: "captcha required"` and moves
  on. Add a custom adapter with `BROWSER_BACKEND=chrome-mcp` if you want
  to solve it interactively.
- **Throttling per directory.** Pacing is per-batch (between different
  sites). For retrying the same site, `pacing.same_site_interval_ms`
  governs the minimum wait - `batch_submit.py` checks history before
  retry.
- **Stale submit URLs.** Directories rename `/submit` to `/add-tool` to
  `/get-listed` and back. `generic.js` does pre-flight URL checks and
  records `error: "Page is 404"`. Run `scripts/scout_form.py` against the
  site root to find the new URL.

## Audit trail

Every submission writes to two places:

1. `submission_history.json` - append-only JSON log, one entry per attempt
   with: site, target_url, adapter, backend, dry_run, submitted, error,
   final_url, screenshot paths, timestamp.
2. `dry-run-output/<slug>-<ts>-before.png` and `*-after.png` - full-page
   screenshots from each submission. Keep these as evidence for support
   tickets ("you said our submission was rejected for incomplete form,
   here is what was on screen when we submitted").

Inspect the log:

```bash
# Show counts by site
python -c "import json; h=json.load(open('submission_history.json')); from collections import Counter; print(Counter(x['site'] for x in h))"

# Show failures
python -c "import json; h=json.load(open('submission_history.json')); [print(x['site'], x.get('error')) for x in h if x.get('error')]"
```

## Estimated cost

- **This skill, free path:** $0 per submission. Playwright runs locally,
  the JS in this repo is MIT.
- **Compared to Apify Store directory submission actors:** ~$0.90 per
  submission, so the full 80-target queue would cost ~$72.
- **Compared to manual submission via VA:** ~30 min per site at $15/hr =
  $7.50 per submission, ~$600 for the queue.

The skill amortises the cost of writing custom adapters across every
future product you list. Adding a new product is just a new
`product-profile.yaml`.
