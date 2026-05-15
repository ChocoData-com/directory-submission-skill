// adapters/_browser.js
//
// Browser-backend abstraction. Returns a `page` object with a stable API
// regardless of whether we are driving Playwright, Playwright-MCP, or
// Stagehand. The script-level orchestrator (scripts/submit_one.py) picks
// the backend via the BROWSER_BACKEND env var and passes it in.
//
// Supported backends:
//   - playwright       : direct playwright (always works, simplest)
//   - playwright-mcp   : @playwright/mcp - same API surface via MCP
//   - stagehand        : @browserbasehq/stagehand - LLM-driven actions
//   - chrome-mcp       : Claude-in-Chrome - the user's logged-in browser
//
// If none of the optional backends are installed, we fall back to plain
// playwright with a clear warning. If playwright itself isn't installed,
// throw with install instructions.

const BACKENDS = ["playwright", "playwright-mcp", "stagehand", "chrome-mcp"];

export async function pickBackend(requested) {
  const want = (requested || process.env.BROWSER_BACKEND || "auto").toLowerCase();

  if (want === "auto") {
    // Probe in order of preference
    for (const candidate of ["playwright-mcp", "stagehand", "playwright"]) {
      if (await isAvailable(candidate)) return candidate;
    }
    throw new Error(
      "No browser backend available. Install one of:\n" +
        "  npm install playwright              # easiest\n" +
        "  npm install @playwright/mcp         # for MCP-driven flows\n" +
        "  npm install @browserbasehq/stagehand  # for LLM-driven flows"
    );
  }
  if (!BACKENDS.includes(want)) {
    throw new Error(
      `Unknown BROWSER_BACKEND="${want}". Valid: ${BACKENDS.join(", ")}`
    );
  }
  if (!(await isAvailable(want))) {
    throw new Error(
      `Backend "${want}" requested but not installed. ` +
        `Install it or set BROWSER_BACKEND=auto.`
    );
  }
  return want;
}

async function isAvailable(name) {
  try {
    if (name === "playwright") {
      await import("playwright");
      return true;
    }
    if (name === "playwright-mcp") {
      // @playwright/mcp ships an MCP server; the user runs it externally,
      // but the package being installed is a fair signal it's available.
      await import("@playwright/mcp");
      return true;
    }
    if (name === "stagehand") {
      await import("@browserbasehq/stagehand");
      return true;
    }
    if (name === "chrome-mcp") {
      // Claude-in-Chrome only works inside a Claude session that has the
      // extension connected. From a CLI run we cannot detect it; the user
      // must explicitly opt in via BROWSER_BACKEND=chrome-mcp, and the
      // launching agent is responsible for providing a page handle.
      return false;
    }
  } catch {
    return false;
  }
  return false;
}

export async function launchPage({ backend, headless = true, userAgent } = {}) {
  if (backend === "playwright" || backend === "playwright-mcp") {
    // playwright-mcp speaks the playwright protocol, so we drive it the
    // same way. The MCP server itself is launched by the host (Claude
    // Code) — here we just need a Browser handle.
    const { chromium } = await import("playwright");
    const browser = await chromium.launch({
      headless,
      args: [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
      ],
    });
    const context = await browser.newContext({
      userAgent:
        userAgent ||
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      viewport: { width: 1440, height: 900 },
      locale: "en-US",
    });
    const page = await context.newPage();
    return {
      page,
      async close() {
        await browser.close();
      },
    };
  }
  if (backend === "stagehand") {
    const { Stagehand } = await import("@browserbasehq/stagehand");
    const sh = new Stagehand({
      env: "LOCAL",
      headless,
      verbose: 1,
    });
    await sh.init();
    return {
      page: sh.page,
      stagehand: sh,
      async close() {
        await sh.close();
      },
    };
  }
  throw new Error(`launchPage: unsupported backend "${backend}"`);
}

export function jitterDelay(ms) {
  const jitter = Math.random() * ms * 0.3;
  return new Promise((r) => setTimeout(r, ms + jitter));
}
