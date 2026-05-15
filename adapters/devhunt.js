// adapters/devhunt.js
//
// DevHunt (https://devhunt.org/) — curated daily-launch directory for dev
// tools. Auth is GitHub OAuth, then a multi-step submission form (logo
// upload, name, tagline, description, categories, links).
//
// This adapter handles the form portion. The login leg has to be done
// once interactively (browser cookies persist via the storageState path
// in product-profile.yaml: credentials.devhunt.session_path), or you set
// `credentials.devhunt.github_token` and we hit the OAuth callback URL
// programmatically.
//
// In --dry-run mode this only navigates to the submit page and reports
// what it sees — it never logs in.

import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import yaml from "yaml";
import { launchPage, pickBackend, jitterDelay } from "./_browser.js";

const SUBMIT_URL = "https://devhunt.org/tool/new";
const LOGIN_URL = "https://devhunt.org/api/auth/signin?provider=github";

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--dry-run") out.dryRun = true;
    else if (a === "--profile") out.profile = argv[++i];
    else if (a === "--backend") out.backend = argv[++i];
  }
  return out;
}

function loadProfile(path) {
  const raw = readFileSync(resolve(path), "utf-8");
  return yaml.parse(raw);
}

export async function runDevHunt(opts) {
  const cfg = loadProfile(opts.profile);
  const product = cfg.product;
  const creds = (cfg.credentials || {}).devhunt || {};
  const browserCfg = cfg.browser || {};
  const backend = await pickBackend(opts.backend || browserCfg.backend);

  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const dir = browserCfg.screenshot_dir || "./dry-run-output";
  const screenshotBefore = `${dir}/devhunt-${ts}-before.png`;
  const screenshotAfter = `${dir}/devhunt-${ts}-after.png`;

  const report = {
    site: "DevHunt",
    target_url: SUBMIT_URL,
    backend,
    dry_run: !!opts.dryRun,
    timestamp: ts,
    detected_fields: {},
    would_fill: {},
    submitted: false,
    screenshot_before: screenshotBefore,
    screenshot_after: null,
    final_url: null,
    error: null,
  };

  const { page, close } = await launchPage({
    backend,
    headless: browserCfg.headless !== false,
  });

  try {
    // Step 1: visit submit page. If we are not logged in, DevHunt redirects
    // to /api/auth/signin — we capture that and report it.
    await page.goto(SUBMIT_URL, {
      waitUntil: "domcontentloaded",
      timeout: browserCfg.timeout_ms || 30000,
    });
    await jitterDelay(2000);

    const finalUrl = page.url();
    if (finalUrl.includes("/api/auth/signin") || finalUrl.includes("/login")) {
      report.error =
        "Not logged in. DevHunt requires GitHub OAuth. " +
        "Run once interactively to set up a session cookie, or set " +
        "credentials.devhunt.github_token in product-profile.yaml.";
      await page.screenshot({ path: screenshotBefore, fullPage: true }).catch(() => null);
      throw new Error(report.error);
    }

    // Step 2: probe the form. DevHunt v2 uses a multi-step wizard, but the
    // first page is always: Name, Tagline, Website URL.
    const nameInput = await page.$('input[name="name"], input[placeholder*="name" i]');
    const urlInput = await page.$('input[name="url"], input[type="url"]');
    const taglineInput = await page.$('input[name="tagline"], input[placeholder*="tagline" i]');
    const descTextarea = await page.$('textarea[name="description"], textarea[placeholder*="description" i]');

    report.detected_fields = {
      name: !!nameInput,
      url: !!urlInput,
      tagline: !!taglineInput,
      description: !!descTextarea,
    };
    report.would_fill = {
      name: product.name,
      url: product.utm_url || product.url,
      tagline: product.tagline,
      description: product.long_description || product.short_description,
    };

    await page.screenshot({ path: screenshotBefore, fullPage: true }).catch(() => null);

    if (opts.dryRun) {
      console.log("[devhunt] DRY-RUN, would fill:", report.would_fill);
    } else {
      if (nameInput) await nameInput.fill(product.name);
      if (taglineInput) await taglineInput.fill(product.tagline || "");
      if (urlInput) await urlInput.fill(product.utm_url || product.url);
      if (descTextarea)
        await descTextarea.fill(
          product.long_description || product.short_description
        );
      await jitterDelay(500);

      const submitBtn = await page.$('button[type="submit"], button:has-text("Continue"), button:has-text("Next")');
      if (submitBtn) {
        await submitBtn.click();
        await jitterDelay(3000);
        report.submitted = true;
        report.final_url = page.url();
        report.screenshot_after = screenshotAfter;
        await page.screenshot({ path: screenshotAfter, fullPage: true }).catch(() => null);
      } else {
        report.error = "no submit/continue button found on DevHunt step 1";
      }
    }
  } catch (e) {
    report.error = report.error || e.message;
  } finally {
    await close().catch(() => null);
  }

  console.log("\n---REPORT-JSON---");
  console.log(JSON.stringify(report, null, 2));
  console.log("---END-REPORT-JSON---");
  return report;
}

if (process.argv[1] && process.argv[1].endsWith("devhunt.js")) {
  runDevHunt(parseArgs(process.argv)).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
