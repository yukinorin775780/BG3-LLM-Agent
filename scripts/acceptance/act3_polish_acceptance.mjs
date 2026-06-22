#!/usr/bin/env node
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

class AcceptanceError extends Error {
  constructor(category, message, details = {}) {
    super(message);
    this.name = "AcceptanceError";
    this.category = category || "product";
    this.details = details;
  }
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");
const startedProcesses = [];
const run = {
  startedAt: new Date().toISOString(),
  stages: [],
  failures: [],
  toolchain: {
    status: "PENDING",
    browserMode: "",
    server: {},
    cdp: {},
  },
  product: {
    status: "PENDING",
  },
};

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const raw = argv[i];
    if (!raw.startsWith("--")) continue;
    const eq = raw.indexOf("=");
    if (eq >= 0) {
      args[raw.slice(2, eq)] = raw.slice(eq + 1);
      continue;
    }
    const key = raw.slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith("--")) {
      args[key] = next;
      i += 1;
    } else {
      args[key] = "true";
    }
  }
  return args;
}

const cli = parseArgs(process.argv.slice(2));
const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
const sessionId = cli["session-id"] || `act3_polish_${stamp}`;
const host = cli.host || "127.0.0.1";
const port = Number(cli.port || 8010);
const serverUrl = (cli["server-url"] || `http://${host}:${port}`).replace(/\/+$/, "");
const mapId = cli["map-id"] || "necromancer_lab";
const browserMode = (cli.browser || process.env.BG3_ACCEPTANCE_BROWSER || "cdp").toLowerCase();
const cdpUrl = cli["cdp-url"] || process.env.BG3_CDP_URL || "http://127.0.0.1:9222";
const captureWidth = Number(cli.width || process.env.BG3_CAPTURE_WIDTH || 1920);
const captureHeight = Number(cli.height || process.env.BG3_CAPTURE_HEIGHT || 1080);
const startServer = cli["no-start-server"] !== "true";
const launchCdp = cli["launch-cdp"] === "true";
const headed = cli.headless === "true" ? false : true;
const outputDir = path.resolve(cli["out-dir"] || `/private/tmp/bg3_act3_polish_${sessionId}`);
const screenshotDir = path.join(outputDir, "screenshots");
const stateDir = path.join(outputDir, "state");
const reportPath = path.join(outputDir, "summary.json");

run.sessionId = sessionId;
run.mapId = mapId;
run.serverUrl = serverUrl;
run.screenshotDir = screenshotDir;
run.stateSnapshotDir = stateDir;
run.summaryPath = reportPath;
run.toolchain.browserMode = browserMode;
run.toolchain.viewport = { width: captureWidth, height: captureHeight };

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function sanitizeName(value) {
  return String(value || "stage").replace(/[^a-z0-9._-]+/gi, "_").replace(/^_+|_+$/g, "");
}

async function writeJson(filePath, data) {
  await fs.writeFile(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

async function fetchJson(url, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} ${response.statusText}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function waitForHttp(url, timeoutMs = 15000) {
  const started = Date.now();
  let lastError = null;
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok || response.status < 500) return { ok: true, status: response.status };
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await sleep(300);
  }
  return { ok: false, error: lastError ? String(lastError.message || lastError) : "timeout" };
}

async function ensureServer() {
  const probeUrl = `${serverUrl}/web_ui/`;
  let probe = await waitForHttp(probeUrl, 2500);
  if (probe.ok) {
    run.toolchain.server = { status: "CONNECTED", url: serverUrl, startedByScript: false };
    return;
  }
  if (!startServer) {
    throw new AcceptanceError("tooling_server", `Server is not reachable at ${serverUrl}`, { probe });
  }

  const python = cli.python || process.env.PYTHON || "python";
  const proc = spawn(python, ["server.py", "--host", host, "--port", String(port)], {
    cwd: repoRoot,
    env: { ...process.env, BG3_HOST: host, BG3_PORT: String(port) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  proc.stdout.on("data", (chunk) => {
    stdout += String(chunk);
    if (stdout.length > 12000) stdout = stdout.slice(-12000);
  });
  proc.stderr.on("data", (chunk) => {
    stderr += String(chunk);
    if (stderr.length > 12000) stderr = stderr.slice(-12000);
  });
  startedProcesses.push({ name: "server", proc });

  probe = await waitForHttp(probeUrl, 20000);
  if (!probe.ok) {
    throw new AcceptanceError("tooling_server", "Failed to start local server", {
      url: serverUrl,
      probe,
      stdout,
      stderr,
      exitCode: proc.exitCode,
    });
  }
  run.toolchain.server = { status: "STARTED", url: serverUrl, startedByScript: true };
}

async function ensureCdpChrome() {
  const versionUrl = `${cdpUrl.replace(/\/+$/, "")}/json/version`;
  let probe = await waitForHttp(versionUrl, 1000);
  if (probe.ok) {
    run.toolchain.cdp = { status: "CONNECTED", url: cdpUrl, launchedByScript: false };
    return;
  }
  if (!launchCdp) {
    throw new AcceptanceError("tooling_browser", `CDP endpoint is not reachable at ${cdpUrl}`, { probe });
  }

  const userDataDir = cli["cdp-user-data-dir"] || `/private/tmp/bg3_chrome_acceptance_profile_${sessionId}`;
  await fs.mkdir(userDataDir, { recursive: true });
  const openArgs = [
    "-na",
    "Google Chrome",
    "--args",
    `--remote-debugging-port=${new URL(cdpUrl).port || "9222"}`,
    `--user-data-dir=${userDataDir}`,
    "--no-first-run",
    "--disable-default-apps",
    "--disable-popup-blocking",
    `--window-size=${captureWidth},${captureHeight}`,
  ];
  const proc = spawn("open", openArgs, {
    cwd: repoRoot,
    stdio: "ignore",
    detached: true,
  });
  proc.unref();

  probe = await waitForHttp(versionUrl, 15000);
  if (!probe.ok) {
    throw new AcceptanceError("tooling_browser", "Failed to launch Chrome CDP via macOS open", {
      cdpUrl,
      userDataDir,
      probe,
    });
  }
  run.toolchain.cdp = { status: "STARTED", url: cdpUrl, launchedByScript: true, userDataDir };
}

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch (error) {
    throw new AcceptanceError("tooling_dependency", "Playwright is not importable from this repo", {
      error: String(error.message || error),
      hint: "Run: npm install -D @playwright/test playwright",
    });
  }
}

async function launchBrowser(playwright) {
  const { chromium } = playwright;
  if (browserMode === "cdp") {
    await ensureCdpChrome();
    const browser = await chromium.connectOverCDP(cdpUrl);
    const context = browser.contexts()[0] || await browser.newContext();
    const page = context.pages()[0] || await context.newPage();
    await page.setViewportSize({ width: captureWidth, height: captureHeight }).catch(() => {});
    return { browser, context, page, ownsBrowser: false };
  }
  if (browserMode === "chromium") {
    const browser = await chromium.launch({
      headless: !headed,
      args: [`--window-size=${captureWidth},${captureHeight}`],
    });
    const context = await browser.newContext({ viewport: { width: captureWidth, height: captureHeight } });
    const page = await context.newPage();
    return { browser, context, page, ownsBrowser: true };
  }
  throw new AcceptanceError("tooling_browser", `Unsupported browser mode: ${browserMode}`);
}

async function frontendSnapshot(page) {
  return await page.evaluate(() => {
    const byId = (id) => document.getElementById(id);
    const text = (selector) => Array.from(document.querySelectorAll(selector))
      .map((el) => (el.textContent || "").replace(/\s+/g, " ").trim())
      .filter(Boolean);
    const visibleText = (selector) => Array.from(document.querySelectorAll(selector))
      .filter((el) => {
        const style = window.getComputedStyle(el);
        return style.visibility !== "hidden" && style.display !== "none";
      })
      .map((el) => (el.textContent || "").replace(/\s+/g, " ").trim())
      .filter(Boolean);
    const inputController = window.BG3InputController || {};
    const hud = window.BG3HudRenderers || {};
    const tactical = window.BG3TacticalMap || {};
    const safeCall = (fn, fallback) => {
      try {
        return typeof fn === "function" ? fn() : fallback;
      } catch (_error) {
        return fallback;
      }
    };
    const highlighted = safeCall(inputController.getCurrentHighlightedInteractable, null);
    const playerPosition = safeCall(inputController.getPlayerPosition, null);
    return {
      url: window.location.href,
      title: (byId("act-title")?.textContent || "").trim(),
      location: (byId("current-location")?.textContent || "").trim(),
      summary: (byId("act-summary")?.textContent || "").trim(),
      hint: (byId("interaction-hint")?.textContent || "").trim(),
      directorMode: (byId("director-trace-mode")?.textContent || "").trim(),
      directorSummary: (byId("director-trace-summary")?.textContent || "").trim(),
      directorState: (byId("director-state-indicator")?.textContent || "").trim(),
      input: {
        playerPosition,
        highlighted,
      },
      tacticalPlayer: safeCall(tactical.getPlayerGridPosition, null),
      barkDebug: safeCall(hud.getCompanionBarkDebugState, null),
      qaState: window.__BG3_QA_STATE__ || null,
      diceCards: text(".dice-card"),
      signalCards: text(".agent-signal-card"),
      memoryCards: text(".memory-card"),
      barks: visibleText(".companion-bark"),
      toasts: text(".hud-toast"),
      lootModalVisible: !byId("loot-modal")?.classList.contains("hidden"),
      bodyTextSample: (document.body?.innerText || "").slice(0, 8000),
    };
  });
}

async function backendSnapshot() {
  const url = `${serverUrl}/api/state?session_id=${encodeURIComponent(sessionId)}&map_id=${encodeURIComponent(mapId)}`;
  return await fetchJson(url, 10000);
}

async function saveStage(page, name, extra = {}) {
  const index = String(run.stages.length + 1).padStart(2, "0");
  const safe = `${index}_${sanitizeName(name)}`;
  const screenshotPath = path.join(screenshotDir, `${safe}.png`);
  const statePath = path.join(stateDir, `${safe}.json`);
  const front = await frontendSnapshot(page).catch((error) => ({ error: String(error.message || error) }));
  const back = await backendSnapshot().catch((error) => ({ error: String(error.message || error) }));
  await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
  const snapshot = { stage: name, savedAt: new Date().toISOString(), frontend: front, backend: back, extra };
  await writeJson(statePath, snapshot);
  const record = {
    name,
    screenshotPath,
    statePath,
    title: front.title || "",
    hint: front.hint || "",
    highlighted: front.input?.highlighted?.id || "",
    playerPosition: front.input?.playerPosition || null,
    visibleRooms: back.map_data?.visible_rooms || back.visible_rooms || [],
    flags: back.flags || back.game_state?.flags || {},
  };
  run.stages.push(record);
  return snapshot;
}

function productAssert(condition, message, details = {}) {
  if (!condition) throw new AcceptanceError("product", message, details);
}

function selectorAssert(condition, message, details = {}) {
  if (!condition) throw new AcceptanceError("selector", message, details);
}

async function waitForSelector(page, selector, timeout = 12000) {
  try {
    await page.waitForSelector(selector, { timeout });
  } catch (error) {
    throw new AcceptanceError("selector", `Missing selector ${selector}`, { error: String(error.message || error) });
  }
}

async function waitSettled(page, delayMs = 800) {
  await page.waitForLoadState("domcontentloaded").catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 2500 }).catch(() => {});
  await page.waitForFunction(() => {
    const btn = document.getElementById("dock-send-btn");
    return !btn || btn.disabled !== true;
  }, { timeout: 12000 }).catch(() => {});
  await sleep(delayMs);
}

async function focusGame(page) {
  await page.locator("#map-stage").click({ position: { x: 520, y: 420 }, timeout: 5000 }).catch(async () => {
    await page.mouse.click(520, 420);
  });
  await page.evaluate(() => {
    const active = document.activeElement;
    if (active && typeof active.blur === "function") active.blur();
  });
}

async function pressGameKey(page, key, delayMs = 220) {
  await focusGame(page);
  await page.keyboard.press(key);
  await sleep(delayMs);
}

async function currentPosition(page) {
  const snap = await frontendSnapshot(page);
  return snap.input?.playerPosition || null;
}

async function highlightedId(page) {
  const snap = await frontendSnapshot(page);
  return String(snap.input?.highlighted?.id || "").trim();
}

async function walkTo(page, target, options = {}) {
  const maxSteps = Number(options.maxSteps || 80);
  const tolerance = Number(options.tolerance || 0);
  const label = options.label || `${target.x},${target.y}`;
  for (let i = 0; i < maxSteps; i += 1) {
    const pos = await currentPosition(page);
    if (!pos || !Number.isFinite(Number(pos.x)) || !Number.isFinite(Number(pos.y))) {
      throw new AcceptanceError("selector", "Unable to read frontend player position", { target, label });
    }
    const dx = Number(target.x) - Number(pos.x);
    const dy = Number(target.y) - Number(pos.y);
    if (Math.abs(dx) + Math.abs(dy) <= tolerance) return pos;

    const preferred = [];
    if (Math.abs(dy) >= Math.abs(dx)) {
      if (dy < 0) preferred.push("w");
      if (dy > 0) preferred.push("s");
      if (dx < 0) preferred.push("a");
      if (dx > 0) preferred.push("d");
    } else {
      if (dx < 0) preferred.push("a");
      if (dx > 0) preferred.push("d");
      if (dy < 0) preferred.push("w");
      if (dy > 0) preferred.push("s");
    }
    ["w", "a", "s", "d"].forEach((key) => {
      if (!preferred.includes(key)) preferred.push(key);
    });

    let moved = false;
    for (const key of preferred) {
      const before = await currentPosition(page);
      await pressGameKey(page, key);
      const after = await currentPosition(page);
      if (after && before && (Number(after.x) !== Number(before.x) || Number(after.y) !== Number(before.y))) {
        moved = true;
        break;
      }
    }
    if (!moved) {
      throw new AcceptanceError("product", `Player could not move toward ${label}`, {
        target,
        position: await currentPosition(page),
        hint: (await frontendSnapshot(page)).hint,
      });
    }
  }
  throw new AcceptanceError("product", `Exceeded movement budget toward ${label}`, {
    target,
    position: await currentPosition(page),
  });
}

async function sendDockText(page, text) {
  await waitForSelector(page, "#dock-input");
  const input = page.locator("#dock-input");
  await input.click();
  await input.fill(text);
  const responsePromise = page.waitForResponse((response) => response.url().includes("/api/chat"), { timeout: 16000 }).catch(() => null);
  await page.locator("#dock-send-btn").click();
  const response = await responsePromise;
  await waitSettled(page, 1000);
  return response ? { status: response.status(), url: response.url() } : null;
}

async function pressE(page, waitForBackend = true) {
  const responsePromise = waitForBackend
    ? page.waitForResponse((response) => response.url().includes("/api/chat"), { timeout: 16000 }).catch(() => null)
    : Promise.resolve(null);
  await pressGameKey(page, "e", 300);
  const response = await responsePromise;
  await waitSettled(page, 1000);
  return response ? { status: response.status(), url: response.url() } : null;
}

function flagsOf(snapshot) {
  return snapshot.backend?.flags || snapshot.backend?.game_state?.flags || {};
}

function visibleRoomsOf(snapshot) {
  return snapshot.backend?.map_data?.visible_rooms || snapshot.backend?.visible_rooms || [];
}

function textBlob(snapshot) {
  return [
    snapshot.frontend?.title,
    snapshot.frontend?.summary,
    snapshot.frontend?.hint,
    snapshot.frontend?.directorMode,
    snapshot.frontend?.directorSummary,
    snapshot.frontend?.directorState,
    ...(snapshot.frontend?.diceCards || []),
    ...(snapshot.frontend?.signalCards || []),
    ...(snapshot.frontend?.memoryCards || []),
    ...(snapshot.frontend?.barks || []),
    ...(snapshot.frontend?.toasts || []),
    snapshot.frontend?.bodyTextSample,
  ].join("\n");
}

function countMatches(values, pattern) {
  return values.filter((value) => pattern.test(String(value || ""))).length;
}

async function runAcceptance(page) {
  const url = `${serverUrl}/web_ui/?session_id=${encodeURIComponent(sessionId)}&map_id=${encodeURIComponent(mapId)}`;
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  await waitForSelector(page, "#dock-input");
  await waitSettled(page, 1200);

  let stage = await saveStage(page, "act1_initial");
  productAssert(/Act 1|安全屋/.test(stage.frontend.title), "Initial act card is not Act 1", { title: stage.frontend.title });
  productAssert(!/gribbo|boss|实验室深处|毒气阀门/i.test(textBlob(stage)), "Early Gribbo/Boss bark or lab pollution is visible in Act1");
  productAssert(!/Hidden Trap|Trap Disarmed|trap_disarmed|healing baseline/i.test(textBlob(stage)), "Act1 starts with trap/healing stale UI");

  await walkTo(page, { x: 5, y: 17 }, { label: "A-B door approach" });
  stage = await saveStage(page, "act1_ab_door_hint");
  productAssert(/door_a_to_b/.test(stage.frontend.hint), "A-B door E hint did not appear", { hint: stage.frontend.hint });

  await pressE(page, true);
  stage = await saveStage(page, "act2_corridor_visible");
  productAssert(/Act 2|走廊|corridor/i.test(`${stage.frontend.title}\n${stage.frontend.summary}`), "Act2 corridor is not visible after opening A-B door", { title: stage.frontend.title });
  productAssert(visibleRoomsOf(stage).includes("room_b_corridor"), "Backend room_b_corridor is not visible after A-B door", { visibleRooms: visibleRoomsOf(stage) });

  await walkTo(page, { x: 5, y: 12 }, { label: "trap perception trigger" });
  await waitSettled(page, 2000);
  stage = await saveStage(page, "act2_trap_perception");
  const trapCards = countMatches(stage.frontend.signalCards || [], /Hidden Trap Spotted/i);
  const trapDice = countMatches(stage.frontend.diceCards || [], /Astarion|阿斯代伦|Perception|感知/i);
  productAssert(trapCards <= 1, "Trap perception rendered duplicate Hidden Trap cards", { cards: stage.frontend.signalCards });
  productAssert(trapDice <= 1, "Trap perception rendered duplicate dice cards", { diceCards: stage.frontend.diceCards });
  productAssert(!/Poison Gas Released|毒气释放|green gas/i.test(textBlob(stage)), "Trap gas appeared before trigger/failure");

  await sleep(2200);
  stage = await saveStage(page, "act2_trap_perception_after_poll");
  productAssert(countMatches(stage.frontend.signalCards || [], /Hidden Trap Spotted/i) <= 1, "State poll replayed Hidden Trap card", { cards: stage.frontend.signalCards });

  await sendDockText(page, "阿斯代伦，解除 gas_trap_1。");
  stage = await saveStage(page, "act2_trap_disarm");
  const flagsAfterDisarm = flagsOf(stage);
  const stateText = JSON.stringify(stage.backend || {});
  productAssert(/trap.*disabled|disabled.*trap|trap_disarmed|陷阱解除|disabled/i.test(stateText) || flagsAfterDisarm.act2_trap_disabled === true, "Trap was not disabled after Astarion disarm", { flags: flagsAfterDisarm });
  productAssert(countMatches(stage.frontend.signalCards || [], /Trap Disarmed/i) <= 1, "Trap disarm rendered duplicate card", { cards: stage.frontend.signalCards });

  await walkTo(page, { x: 5, y: 8 }, { label: "B-D locked door" });
  stage = await saveStage(page, "act2_bd_door_hint");
  productAssert(/door_b_to_d/.test(stage.frontend.hint), "B-D door E hint did not appear", { hint: stage.frontend.hint, highlighted: stage.frontend.input?.highlighted });

  await pressE(page, true);
  stage = await saveStage(page, "act2_bd_inspect_secret_hint");
  productAssert(!/Act 4/i.test(stage.frontend.title), "B-D inspect jumped to Act4", { title: stage.frontend.title });
  productAssert(!visibleRoomsOf(stage).includes("room_d_lab"), "B-D inspect revealed room_d_lab", { visibleRooms: visibleRoomsOf(stage) });
  productAssert(/door_b_to_c|cracked_wall|暗门|书房/.test(stage.frontend.hint) || stage.frontend.input?.highlighted?.id === "door_b_to_c", "Secret entrance E hint did not appear after B-D inspect", {
    hint: stage.frontend.hint,
    highlighted: stage.frontend.input?.highlighted,
  });

  if (await highlightedId(page) !== "door_b_to_c") {
    await walkTo(page, { x: 5, y: 8 }, { label: "secret entrance candidate" });
  }
  await pressE(page, true);
  stage = await saveStage(page, "act3_secret_study_entry");
  productAssert(/Act 3|秘密书房|Secret Study/i.test(`${stage.frontend.title}\n${stage.frontend.summary}`), "Act card did not switch to Act3 after secret entrance", { title: stage.frontend.title, summary: stage.frontend.summary });
  productAssert(visibleRoomsOf(stage).includes("room_c_secret_study"), "Backend room_c_secret_study is not visible after secret entry", { visibleRooms: visibleRoomsOf(stage) });
  productAssert(!visibleRoomsOf(stage).includes("room_d_lab"), "Secret study entry revealed room_d_lab", { visibleRooms: visibleRoomsOf(stage) });
  productAssert(!/Trap Disarmed|trap_disarmed/i.test(textBlob(stage)), "Act3 still shows stale Act2 trap_disarmed UI");

  await walkTo(page, { x: 3, y: 10 }, { label: "chemical_notes" });
  stage = await saveStage(page, "act3_chemical_notes_hint");
  productAssert(await highlightedId(page) === "chemical_notes", "chemical_notes is not the E candidate", { hint: stage.frontend.hint, highlighted: stage.frontend.input?.highlighted });
  await pressE(page, true);
  stage = await saveStage(page, "act3_read_chemical_notes");
  productAssert(flagsOf(stage).act3_chemical_notes_seen === true, "Reading chemical_notes did not set act3_chemical_notes_seen", { flags: flagsOf(stage) });
  productAssert(flagsOf(stage).act3_diary_context_gathered === true, "Reading chemical_notes did not gather diary context", { flags: flagsOf(stage) });

  await walkTo(page, { x: 2, y: 12 }, { label: "iron_key_sketch" });
  stage = await saveStage(page, "act3_iron_key_sketch_hint");
  productAssert(await highlightedId(page) === "iron_key_sketch", "iron_key_sketch is not the E candidate", { hint: stage.frontend.hint, highlighted: stage.frontend.input?.highlighted });
  await pressE(page, true);
  stage = await saveStage(page, "act3_read_iron_key_sketch");
  productAssert(flagsOf(stage).act3_key_sketch_seen === true, "Reading iron_key_sketch did not set act3_key_sketch_seen", { flags: flagsOf(stage) });
  productAssert(flagsOf(stage).act3_diary_context_gathered === true, "Reading iron_key_sketch did not keep diary context gathered", { flags: flagsOf(stage) });

  await walkTo(page, { x: 2, y: 10 }, { label: "necromancer_diary" });
  stage = await saveStage(page, "act3_necromancer_diary_hint");
  productAssert(await highlightedId(page) === "necromancer_diary", "necromancer_diary is not the E candidate", { hint: stage.frontend.hint, highlighted: stage.frontend.input?.highlighted });
  await pressE(page, true);
  stage = await saveStage(page, "act3_read_necromancer_diary");
  productAssert(flagsOf(stage).act3_diary_decoded === true, "Diary read did not decode", { flags: flagsOf(stage) });
  productAssert(flagsOf(stage).act3_gribbo_potion_truth_known === true, "Diary read did not reveal Gribbo potion truth", { flags: flagsOf(stage) });
  productAssert(!/Act 4/i.test(stage.frontend.title), "Diary read prematurely switched to Act4", { title: stage.frontend.title });
  productAssert(/diary|日记|leverage|筹码|truth|真相|memory|记忆/i.test(`${stage.frontend.directorSummary}\n${stage.frontend.directorState}\n${stage.frontend.signalCards.join("\n")}\n${stage.frontend.memoryCards.join("\n")}`), "Diary read did not keep Director/HUD on diary leverage");
  productAssert(!/LOCAL EXPLORATION/i.test(stage.frontend.directorMode) || /diary|日记|leverage|筹码|truth|真相|memory|记忆/i.test(stage.frontend.directorSummary), "Director Timeline immediately reverted to Local Exploration after diary", {
    directorMode: stage.frontend.directorMode,
    directorSummary: stage.frontend.directorSummary,
  });

  await walkTo(page, { x: 3, y: 12 }, { label: "study_chest" });
  stage = await saveStage(page, "act3_study_chest_hint");
  productAssert(/study_chest|chest_1|旧木箱|搜刮/.test(`${stage.frontend.hint}\n${JSON.stringify(stage.frontend.input?.highlighted || {})}`), "study_chest is not reachable by E", { hint: stage.frontend.hint, highlighted: stage.frontend.input?.highlighted });
  await pressE(page, true);
  let lootVisible = await page.locator("#loot-modal:not(.hidden)").count().catch(() => 0);
  if (lootVisible > 0) {
    await page.locator("#loot-all-btn").click();
    await waitSettled(page, 1200);
  }
  stage = await saveStage(page, "act3_loot_lab_key");
  productAssert(/lab_key/i.test(JSON.stringify(stage.backend?.player_inventory || stage.backend?.inventory || stage.backend || {})), "Looting study chest did not obtain lab_key", { backend: stage.backend });

  await sendDockText(page, "走到 5,8，靠近 door_b_to_d 实验室门。");
  stage = await saveStage(page, "act3_move_to_bd_with_key");
  productAssert(/door_b_to_d/.test(stage.frontend.hint) || (Number(stage.frontend.input?.playerPosition?.x) === 5 && Number(stage.frontend.input?.playerPosition?.y) === 8), "Text move did not place the player near B-D door", {
    hint: stage.frontend.hint,
    position: stage.frontend.input?.playerPosition,
    highlighted: stage.frontend.input?.highlighted,
  });

  await sendDockText(page, "用 lab_key 打开 door_b_to_d 实验室门，进入实验室面对 Gribbo。");
  stage = await saveStage(page, "act4_boss_lab_entry");
  productAssert(/Act 4|Gribbo|实验室|Boss/i.test(`${stage.frontend.title}\n${stage.frontend.summary}`), "Act4/Boss lab did not appear after opening B-D with lab_key", { title: stage.frontend.title, summary: stage.frontend.summary });
  productAssert(visibleRoomsOf(stage).includes("room_d_lab"), "Backend room_d_lab is not visible after opening B-D", { visibleRooms: visibleRoomsOf(stage) });

  await sendDockText(page, "我们怎么处理他？");
  stage = await saveStage(page, "act4_strategy_barks");
  const barkDebug = stage.frontend.barkDebug || {};
  const barkBlob = JSON.stringify(barkDebug) + "\n" + (stage.frontend.barks || []).join("\n") + "\n" + (stage.frontend.signalCards || []).join("\n");
  productAssert(/astarion/i.test(barkBlob) && /shadowheart/i.test(barkBlob) && /lae'?zel|laezel/i.test(barkBlob), "Act4 boss strategy did not include Astarion, Shadowheart, and Lae'zel", { barkDebug, barks: stage.frontend.barks, cards: stage.frontend.signalCards });

  await sendDockText(page, "用日记真相说服 Gribbo 交出 heavy_iron_key。");
  stage = await saveStage(page, "act4_truth_negotiation_key");
  const finalStateBlob = JSON.stringify(stage.backend || {});
  productAssert(/heavy_iron_key/i.test(finalStateBlob), "Truth negotiation did not obtain heavy_iron_key", { backend: stage.backend });

  if (cli["final-exit"] === "true") {
    await walkTo(page, { x: 18, y: 4 }, { label: "final exit" });
    await pressE(page, true);
    stage = await saveStage(page, "final_exit");
    productAssert(JSON.stringify(stage.backend || {}).includes("demo_cleared"), "Final exit did not set demo_cleared", { backend: stage.backend });
  }
}

async function cleanup() {
  for (const entry of startedProcesses.reverse()) {
    try {
      if (entry.proc && entry.proc.exitCode === null) entry.proc.kill("SIGTERM");
    } catch (_error) {
      // Best-effort cleanup only.
    }
  }
}

async function main() {
  await fs.mkdir(screenshotDir, { recursive: true });
  await fs.mkdir(stateDir, { recursive: true });

  if (!existsSync(path.join(repoRoot, "package.json"))) {
    throw new AcceptanceError("tooling_dependency", "Script must run from the BG3_LLM_Agent repo");
  }

  let browserHandle = null;
  try {
    await ensureServer();
    const playwright = await loadPlaywright();
    browserHandle = await launchBrowser(playwright);
    run.toolchain.status = "PASS";

    await runAcceptance(browserHandle.page);
    run.product.status = "PASS";
  } catch (error) {
    const category = error instanceof AcceptanceError ? error.category : "tooling_unknown";
    const failure = {
      category,
      message: String(error.message || error),
      details: error instanceof AcceptanceError ? error.details : { stack: String(error.stack || "") },
      at: new Date().toISOString(),
    };
    run.failures.push(failure);
    if (category.startsWith("tooling") || category === "selector") {
      run.toolchain.status = "FAIL";
      run.product.status = "NOT_RUN";
    } else {
      run.toolchain.status = "PASS";
      run.product.status = "FAIL";
    }
    if (browserHandle?.page) {
      await saveStage(browserHandle.page, `failure_${category}`).catch(() => {});
    }
    process.exitCode = 1;
  } finally {
    run.finishedAt = new Date().toISOString();
    await writeJson(reportPath, run).catch(() => {});
    if (browserHandle?.context && browserMode !== "cdp") {
      await browserHandle.context.close().catch(() => {});
    }
    if (browserHandle?.browser) {
      await browserHandle.browser.close().catch(() => {});
    }
    await cleanup();
    console.log(JSON.stringify({
      toolchain: run.toolchain.status,
      product: run.product.status,
      browserMode,
      sessionId,
      summaryPath: reportPath,
      screenshotDir,
      stateSnapshotDir: stateDir,
      failures: run.failures,
    }, null, 2));
  }
}

await main();
