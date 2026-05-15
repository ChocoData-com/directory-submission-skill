// adapters/uneed.js
//
// Uneed (https://www.uneed.best/promote-your-tool) — Tally-form-based
// submission. Their UI changes often; we drive the embedded Tally form
// instead of the host page where possible.
//
// Uneed is queued (free tier) — submissions show up after a few days.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import yaml from "yaml";
import { launchPage, pickBackend, jitterDelay } from "./_browser.js";

const SUBMIT_URL = "https://www.uneed.best/promote-your-tool";

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

export async function runUneed(opts) {
  const cfg = loadProfile(opts.profile);
  const product = cfg.product;
  const browserCfg = cfg.browser || {};
  const backend = await pickBackend(opts.backend || browserCfg.backend);

  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const dir = browserCfg.screenshot_dir || "./dry-run-output";
  const shotBefore = `${dir}/uneed-${ts}-before.png`;

  const report = {
    site: "Uneed",
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
    await page.goto(SUBMIT_URL, { waitUntil: "domcontentloaded" });
    await jitterDelay(3000);

    // Tally iframes — try to switch into one if present
    const iframes = page.frames();
    const tallyFrame = iframes.find((f) =>
      f.url().includes("tally.so") || f.name().includes("tally")
    );
    const formContext = tallyFrame || page;

    const nameInput = await formContext.$('input[name*="name" i], input[placeholder*="name" i]');
    const urlInput = await formContext.$('input[name*="url" i], input[type="url"]');
    const descTextarea = await formContext.$('textarea');
    const emailInput = await formContext.$('input[type="email"]');

    report.detected_fields = {
      name: !!nameInput,
      url: !!urlInput,
      description: !!descTextarea,
      email: !!emailInput,
      tally_iframe: !!tallyFrame,
    };
    report.would_fill = {
      name: product.name,
      url: product.utm_url || product.url,
      description: product.long_description || product.short_description,
      email: product.email,
    };

    await page.screenshot({ path: shotBefore, fullPage: true }).catch(() => null);

    if (opts.dryRun) {
      console.log("[uneed] DRY-RUN:", report.would_fill);
    } else {
      if (nameInput) await nameInput.fill(product.name);
      if (urlInput) await urlInput.fill(product.utm_url || product.url);
      if (descTextarea)
        await descTextarea.fill(
          product.long_description || product.short_description
        );
      if (emailInput) await emailInput.fill(product.email);
      await jitterDelay(500);
      const submitBtn = await formContext.$('button[type="submit"], button:has-text("Submit")');
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

if (process.argv[1] && process.argv[1].endsWith("uneed.js")) {
  runUneed(parseArgs(process.argv)).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
