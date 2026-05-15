// adapters/stackshare.js
//
// StackShare (https://stackshare.io/services/new) — service catalog. Auth
// is email/password; the create-service form has Name, Tagline, Website,
// Category (combobox), Description, Logo upload.
//
// Account must already exist. We log in, then fill the form. In --dry-run
// we skip login entirely and only navigate to /services/new (which 302s to
// login) to confirm reachability.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import yaml from "yaml";
import { launchPage, pickBackend, jitterDelay } from "./_browser.js";

const SUBMIT_URL = "https://stackshare.io/services/new";
const LOGIN_URL = "https://stackshare.io/login";

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
  return yaml.parse(readFileSync(resolve(path), "utf-8"));
}

export async function runStackShare(opts) {
  const cfg = loadProfile(opts.profile);
  const product = cfg.product;
  const creds = (cfg.credentials || {}).stackshare || {};
  const browserCfg = cfg.browser || {};
  const backend = await pickBackend(opts.backend || browserCfg.backend);

  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const dir = browserCfg.screenshot_dir || "./dry-run-output";
  const shotBefore = `${dir}/stackshare-${ts}-before.png`;

  const report = {
    site: "StackShare",
    target_url: SUBMIT_URL,
    backend,
    dry_run: !!opts.dryRun,
    timestamp: ts,
    detected_fields: {},
    would_fill: {},
    submitted: false,
    screenshot_before: shotBefore,
    final_url: null,
    error: null,
  };

  const { page, close } = await launchPage({
    backend,
    headless: browserCfg.headless !== false,
  });

  try {
    if (!opts.dryRun) {
      if (!creds.email || !creds.password) {
        throw new Error(
          "StackShare requires credentials.stackshare.email/password in profile"
        );
      }
      await page.goto(LOGIN_URL, { waitUntil: "domcontentloaded" });
      await jitterDelay(1500);
      await page.fill('input[name="user[email]"], input[type="email"]', creds.email);
      await page.fill('input[name="user[password]"], input[type="password"]', creds.password);
      await page.click('button[type="submit"], input[type="submit"]');
      await jitterDelay(3000);
    }

    await page.goto(SUBMIT_URL, { waitUntil: "domcontentloaded" });
    await jitterDelay(2000);

    const nameInput = await page.$('input[name*="name" i]');
    const urlInput = await page.$('input[name*="url" i], input[type="url"]');
    const taglineInput = await page.$('input[name*="tagline" i], input[placeholder*="tagline" i]');
    const descTextarea = await page.$("textarea");
    const submitBtn = await page.$('button[type="submit"], input[type="submit"]');

    report.detected_fields = {
      name: !!nameInput,
      url: !!urlInput,
      tagline: !!taglineInput,
      description: !!descTextarea,
      submit: !!submitBtn,
    };
    report.would_fill = {
      name: product.name,
      url: product.utm_url || product.url,
      tagline: product.tagline,
      description: product.long_description || product.short_description,
    };

    await page.screenshot({ path: shotBefore, fullPage: true }).catch(() => null);

    if (opts.dryRun) {
      console.log("[stackshare] DRY-RUN:", report.would_fill);
    } else {
      if (nameInput) await nameInput.fill(product.name);
      if (urlInput) await urlInput.fill(product.utm_url || product.url);
      if (taglineInput) await taglineInput.fill(product.tagline || "");
      if (descTextarea)
        await descTextarea.fill(
          product.long_description || product.short_description
        );
      await jitterDelay(500);
      if (submitBtn) {
        await submitBtn.click();
        await jitterDelay(3000);
        report.submitted = true;
        report.final_url = page.url();
      } else {
        report.error = "no submit button found";
      }
    }
  } catch (e) {
    report.error = e.message;
  } finally {
    await close().catch(() => null);
  }

  console.log("\n---REPORT-JSON---");
  console.log(JSON.stringify(report, null, 2));
  console.log("---END-REPORT-JSON---");
  return report;
}

if (process.argv[1] && process.argv[1].endsWith("stackshare.js")) {
  runStackShare(parseArgs(process.argv)).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
