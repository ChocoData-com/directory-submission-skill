// adapters/generic.js
//
// Accessibility-tree based fallback adapter. Works on most "fill the form,
// click submit" directories by pattern-matching field labels.
//
// Adapted from s87343472/backlink-pilot/src/sites/generic.js (MIT).
//
// CLI usage (called by scripts/submit_one.py):
//   node adapters/generic.js \
//     --profile product-profile.yaml \
//     --target "https://devhunt.org/submit" \
//     --dry-run

import { readFileSync } from "node:fs";
import { resolve, basename } from "node:path";
import yaml from "yaml";
import { launchPage, pickBackend, jitterDelay } from "./_browser.js";

const FIELD_PATTERNS = {
  name: /name|title|product|app.?name|tool.?name/i,
  url: /url|website|link|homepage|site/i,
  email: /email|mail|e-?mail/i,
  description: /desc|description|about|summary|detail|intro|tagline/i,
  twitter: /twitter|x[- ]handle/i,
  github: /github|repo/i,
  category: /category|tag|topic/i,
};

const SUBMIT_PATTERNS = /submit|send|add|post|create|list|suggest|save/i;

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--dry-run") out.dryRun = true;
    else if (a.startsWith("--profile=")) out.profile = a.slice(10);
    else if (a === "--profile") out.profile = argv[++i];
    else if (a.startsWith("--target=")) out.target = a.slice(9);
    else if (a === "--target") out.target = argv[++i];
    else if (a.startsWith("--backend=")) out.backend = a.slice(10);
    else if (a === "--backend") out.backend = argv[++i];
    else if (a.startsWith("--site-name=")) out.siteName = a.slice(12);
    else if (a === "--site-name") out.siteName = argv[++i];
  }
  return out;
}

function loadProfile(path) {
  if (!path) throw new Error("--profile is required");
  const raw = readFileSync(resolve(path), "utf-8");
  const parsed = yaml.parse(raw);
  if (!parsed?.product) throw new Error("profile YAML missing `product:` key");
  return parsed;
}

function safeFile(s) {
  return s.replace(/[^a-z0-9.-]/gi, "_").slice(0, 80);
}

async function buildAriaSnapshot(page) {
  // Build a stable text snapshot from the page accessibility tree.
  // For Playwright we can call accessibility.snapshot(); we also collect
  // input/textarea/button elements as a fallback for sites where the
  // accessibility tree is sparse.
  const inputs = await page.$$eval(
    "input, textarea, select, button, a[role=button]",
    (els) =>
      els.map((el, i) => {
        const tag = el.tagName.toLowerCase();
        const role =
          el.getAttribute("role") ||
          (tag === "textarea"
            ? "textbox"
            : tag === "select"
            ? "combobox"
            : tag === "button"
            ? "button"
            : el.type === "submit"
            ? "button"
            : "textbox");
        const label =
          el.getAttribute("aria-label") ||
          el.getAttribute("placeholder") ||
          el.getAttribute("name") ||
          el.getAttribute("id") ||
          el.textContent?.trim().slice(0, 80) ||
          "";
        return { ref: `@${i}`, role, label, tag, type: el.type || "" };
      })
  );
  return inputs;
}

function detectFields(snapshot) {
  const found = {
    name: null,
    url: null,
    email: null,
    description: null,
    twitter: null,
    github: null,
    category: null,
    submit: null,
  };
  for (const item of snapshot) {
    const label = item.label || "";
    if (item.role === "button" || item.type === "submit") {
      if (!found.submit && SUBMIT_PATTERNS.test(label)) {
        found.submit = item.ref;
      }
      continue;
    }
    if (item.role !== "textbox" && item.role !== "combobox") continue;
    for (const key of Object.keys(FIELD_PATTERNS)) {
      if (found[key]) continue;
      if (FIELD_PATTERNS[key].test(label)) {
        found[key] = item.ref;
        break;
      }
    }
  }
  return found;
}

function valuesFromProfile(product) {
  return {
    name: product.name,
    url: product.utm_url || product.url,
    email: product.email,
    description: product.long_description || product.short_description,
    twitter: product.twitter || "",
    github: product.github ? `https://github.com/${product.github}` : "",
    category: (product.categories && product.categories[0]) || "",
  };
}

async function fillByRef(page, snapshot, ref, value) {
  const item = snapshot.find((s) => s.ref === ref);
  if (!item) return false;
  const idx = parseInt(item.ref.slice(1), 10);
  // Use playwright locator with nth selector matching our snapshot indexing
  const handle = await page.$(
    `:is(input, textarea, select, button, a[role=button]) >> nth=${idx}`
  );
  if (!handle) return false;
  if (item.role === "combobox" && item.tag === "select") {
    await handle.selectOption({ label: value }).catch(() => null);
  } else {
    await handle.fill(value).catch(() => null);
  }
  return true;
}

export async function runGeneric(opts) {
  const { profile, target, siteName, dryRun, backend } = opts;
  const cfg = loadProfile(profile);
  const product = cfg.product;
  const browserCfg = cfg.browser || {};
  const screenshotDir = browserCfg.screenshot_dir || "./dry-run-output";

  const usedBackend = await pickBackend(backend || browserCfg.backend);
  console.log(`[generic] backend=${usedBackend} target=${target}`);

  const { page, close } = await launchPage({
    backend: usedBackend,
    headless: browserCfg.headless !== false,
    userAgent: browserCfg.user_agent || null,
  });

  const slug = safeFile(siteName || new URL(target).hostname);
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const screenshotBefore = `${screenshotDir}/${slug}-${ts}-before.png`;
  const screenshotAfter = `${screenshotDir}/${slug}-${ts}-after.png`;
  const report = {
    site: siteName || target,
    target_url: target,
    backend: usedBackend,
    dry_run: !!dryRun,
    timestamp: ts,
    detected_fields: {},
    would_fill: {},
    submitted: false,
    screenshot_before: screenshotBefore,
    screenshot_after: null,
    final_url: null,
    error: null,
  };

  try {
    await page.goto(target, {
      waitUntil: "domcontentloaded",
      timeout: browserCfg.timeout_ms || 30000,
    });
    await jitterDelay(2000);

    // Defensive page checks
    const title = await page.title().catch(() => "");
    const bodyText = (await page.textContent("body").catch(() => "")) || "";
    const snippet = bodyText.slice(0, 500).toLowerCase();
    if (/404|not found|page not found/.test(snippet) || /404/.test(title)) {
      throw new Error("Page is 404 — submit URL is stale");
    }
    if (/500|server error|internal error/.test(snippet)) {
      throw new Error("Server returned 5xx — site appears down");
    }

    const snap = await buildAriaSnapshot(page);
    const fields = detectFields(snap);
    report.detected_fields = fields;

    const values = valuesFromProfile(product);
    for (const k of Object.keys(values)) {
      if (fields[k] && values[k]) {
        report.would_fill[k] = values[k];
      }
    }

    // Screenshot of unfilled form
    await page
      .screenshot({ path: screenshotBefore, fullPage: true })
      .catch(() => null);

    if (dryRun) {
      console.log("[generic] DRY-RUN — would fill:");
      for (const [k, v] of Object.entries(report.would_fill)) {
        console.log(`  ${k} => ${typeof v === "string" ? v.slice(0, 80) : v}`);
      }
      console.log(`[generic] screenshot: ${screenshotBefore}`);
      report.submitted = false;
    } else {
      // Actually fill + submit
      for (const k of Object.keys(values)) {
        if (fields[k] && values[k]) {
          await fillByRef(page, snap, fields[k], String(values[k]));
          await jitterDelay(300);
        }
      }
      if (fields.submit) {
        await page.click(`:is(button, input[type=submit], a[role=button]) >> ` +
          `nth=${parseInt(fields.submit.slice(1), 10)}`).catch(() => null);
        await jitterDelay(3000);
        report.submitted = true;
        report.final_url = page.url();
        report.screenshot_after = screenshotAfter;
        await page
          .screenshot({ path: screenshotAfter, fullPage: true })
          .catch(() => null);
      } else {
        report.error = "no submit button detected";
      }
    }
  } catch (err) {
    report.error = err.message || String(err);
    console.error(`[generic] ERROR: ${report.error}`);
  } finally {
    await close().catch(() => null);
  }

  // Print structured JSON the Python orchestrator will parse
  console.log("\n---REPORT-JSON---");
  console.log(JSON.stringify(report, null, 2));
  console.log("---END-REPORT-JSON---");
  return report;
}

// Allow direct CLI invocation
if (import.meta.url === `file://${process.argv[1].replace(/\\/g, "/")}` ||
    basename(process.argv[1] || "") === "generic.js") {
  const args = parseArgs(process.argv);
  runGeneric(args).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
