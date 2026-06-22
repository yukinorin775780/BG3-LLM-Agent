import { createRequire } from "node:module";
import fs from "node:fs/promises";

const require = createRequire(import.meta.url);
const { chromium } = require("/Users/zhangxiao/.hermes/hermes-agent/node_modules/playwright");

const repoRoot = "/Users/zhangxiao/BG3_LLM_Agent";
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..*/, "");
const outDir = process.env.BG3_CAPTURE_OUT || `${repoRoot}/artifacts/demo_recording/reaudit_visual_${stamp}`;
const sessionId = process.env.BG3_CAPTURE_SESSION || `reaudit_visual_${stamp}`;
const mapId = "necromancer_lab";
const base = "http://127.0.0.1:8010";
const url = `${base}/web_ui/?session_id=${sessionId}&map_id=${mapId}&qa_no_idle=1`;
const DEFAULT_CAPTURE_WIDTH = 1920;
const DEFAULT_CAPTURE_HEIGHT = 1080;
const DEFAULT_DEVICE_SCALE_FACTOR = 1;
const captureWidth = Number(process.env.BG3_CAPTURE_WIDTH || DEFAULT_CAPTURE_WIDTH);
const captureHeight = Number(process.env.BG3_CAPTURE_HEIGHT || DEFAULT_CAPTURE_HEIGHT);
const deviceScaleFactor = Number(process.env.BG3_DEVICE_SCALE_FACTOR || DEFAULT_DEVICE_SCALE_FACTOR);
const captureSize = { width: captureWidth, height: captureHeight };

await fs.mkdir(`${outDir}/screenshots`, { recursive: true });
await fs.mkdir(`${outDir}/responses`, { recursive: true });

const headless = process.env.BG3_HEADLESS !== "0";
const shouldRecordVideo = process.env.BG3_RECORD_VIDEO === "1";
const rawVideoDir = `${outDir}/raw_video`;
if (shouldRecordVideo) {
  await fs.mkdir(rawVideoDir, { recursive: true });
}
const browser = await chromium.launch({ headless });
const context = await browser.newContext({
  // README demo capture defaults to 1080p so DOM HUD text is not scaled up from 720p.
  viewport: captureSize,
  deviceScaleFactor,
  ...(shouldRecordVideo
    ? {
        recordVideo: {
          dir: rawVideoDir,
          size: captureSize,
        },
      }
    : {}),
});
const page = await context.newPage();
page.setDefaultTimeout(30_000);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function flags(state) {
  return state && typeof state.flags === "object" ? state.flags : {};
}

function visibleRooms(state) {
  return state?.map_data?.visible_rooms || [];
}

function hasVisibleRoom(state, roomId) {
  return visibleRooms(state).includes(roomId);
}

function objectRecord(state, objectId) {
  return state?.environment_objects?.[objectId] || {};
}

function isOpenDoor(state, doorId) {
  const door = objectRecord(state, doorId);
  return door.is_open === true || String(door.status || "").toLowerCase() === "open";
}

function hasItem(state, itemId) {
  return Number(state?.player_inventory?.[itemId] || 0) > 0;
}

async function shot(name) {
  await page.screenshot({ path: `${outDir}/screenshots/${name}.png` });
}

async function state(name) {
  const res = await fetch(`${base}/api/state?session_id=${sessionId}&map_id=${mapId}`);
  const json = await res.json();
  await fs.writeFile(`${outDir}/${name}.state.json`, JSON.stringify(json, null, 2));
  return json;
}

async function waitForStateCondition(name, predicate, timeoutMs = 45_000) {
  const started = Date.now();
  let latest = await state(`${name}.poll`);
  while (Date.now() - started < timeoutMs) {
    if (predicate(latest)) return latest;
    await page.waitForTimeout(500);
    latest = await state(`${name}.poll`);
  }
  throw new Error(`Timed out waiting for state condition after ${name}`);
}

async function waitForPageCondition(name, predicate, timeoutMs = 20_000) {
  const started = Date.now();
  let latest = await predicate();
  while (Date.now() - started < timeoutMs) {
    if (latest) return latest;
    await page.waitForTimeout(250);
    latest = await predicate();
  }
  throw new Error(`Timed out waiting for page condition after ${name}`);
}

async function waitForLocalRoomVisible(name, roomId, timeoutMs = 20_000) {
  return waitForPageCondition(name, async () => page.evaluate((targetRoomId) => {
    const visible = window.BG3TacticalMap?.scene?.mapData?.visible_rooms
      || window.BG3TacticalMap?.scene?.mapData?.visibleRooms
      || [];
    const player = window.BG3InputController?.getPlayerPosition?.() || {};
    const highlighted = window.BG3InputController?.getCurrentHighlightedInteractable?.() || null;
    return Array.isArray(visible) && visible.includes(targetRoomId)
      ? { visible, player, highlighted }
      : null;
  }, roomId), timeoutMs);
}

async function waitForUiSettle(extraMs = 900) {
  await page.waitForTimeout(extraMs);
}

async function send(name, text, options = {}) {
  const {
    timeoutMs = 90_000,
    settleMs = 1000,
    expectState = null,
  } = options;
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/chat") && response.request().method() === "POST",
    { timeout: timeoutMs },
  );
  await page.locator("#dock-input").fill(text);
  await page.locator("#dock-send-btn").click();
  const response = await responsePromise;
  const json = await response.json();
  await fs.writeFile(`${outDir}/responses/${name}.response.json`, JSON.stringify(json, null, 2));
  await waitForUiSettle(settleMs);
  const latest = expectState
    ? await waitForStateCondition(name, expectState, timeoutMs)
    : await state(name);
  await fs.writeFile(`${outDir}/${name}.state.json`, JSON.stringify(latest, null, 2));
  await shot(name);
  return latest;
}

async function focusGame() {
  await page.mouse.click(410, 360);
  await page.waitForTimeout(100);
}

async function press(name, keys, waitMs = 450) {
  await focusGame();
  for (const key of keys) {
    await page.keyboard.press(key);
    await page.waitForTimeout(waitMs);
  }
  await waitForUiSettle(350);
  await shot(name);
  return state(name);
}

async function pressAndWait(name, keys, options = {}) {
  const {
    waitMs = 450,
    settleMs = 1400,
    expectState = null,
    timeoutMs = 45_000,
  } = options;
  await focusGame();
  for (const key of keys) {
    await page.keyboard.press(key);
    await page.waitForTimeout(waitMs);
  }
  await waitForUiSettle(settleMs);
  const latest = expectState
    ? await waitForStateCondition(name, expectState, timeoutMs)
    : await state(name);
  await fs.writeFile(`${outDir}/${name}.state.json`, JSON.stringify(latest, null, 2));
  await shot(name);
  return latest;
}

try {
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForTimeout(1800);
  await shot("00_hook_fresh");
  await state("00_hook_fresh");

  await press("01_act1_local_wasd", ["s", "d", "a"], 350);

  await send("02_ab_door_open", "打开通往毒气走廊的门。", {
    settleMs: 1200,
    expectState: (st) => hasVisibleRoom(st, "room_b_corridor"),
  });

  await focusGame();
  let perception = null;
  for (let i = 1; i <= 10; i += 1) {
    await page.keyboard.press("w");
    await page.waitForTimeout(1400);
    const st = await state(`03_after_w_${i}`);
    assert(
      !st.flags?.act2_gas_trap_triggered && !st.flags?.necromancer_lab_poison_trap_triggered,
      `Trap triggered during approach at step ${i}`,
    );
    if (st.flags?.act2_astarion_perception_checked && st.flags?.act2_gas_trap_revealed) {
      perception = st;
      break;
    }
  }
  assert(perception, "Astarion perception did not trigger");
  await waitForUiSettle(1800);
  await shot("03_astarion_perception");

  await send("04_astarion_disarm", "阿斯代伦，解除陷阱。", {
    settleMs: 1300,
    expectState: (st) => flags(st).necromancer_lab_poison_trap_disarmed === true
      || flags(st).act2_gas_trap_disarmed === true,
  });

  await send("05a_move_lab_door_for_hint", "靠近 B-D 实验室重门。", { settleMs: 900 });
  await send("05b_locked_lab_door_inspect", "检查 B-D 门，不要撬锁。", {
    settleMs: 1200,
    expectState: (st) => flags(st).act2_secret_study_hint_given === true
      && flags(st).act2_secret_study_route_unlocked === true,
  });
  await send("05c_lockpick_fail_hint", "尝试撬锁 door_b_to_d，演示失败。", {
    settleMs: 1500,
    expectState: (st) => flags(st).act2_corridor_exit_lockpick_attempted === true
      && flags(st).act2_corridor_exit_lockpick_success === false
      && flags(st).act2_secret_study_route_unlocked === true,
  });
  await waitForUiSettle(1300);
  await shot("05d_cracked_wall_discovered_stable");
  await state("05d_cracked_wall_discovered_stable");

  await press("05e_secret_wall_inspected", ["e"], 450);
  await waitForUiSettle(900);
  await shot("05f_secret_door_ready");
  await state("05f_secret_door_ready");
  await press("05g_secret_wall_opened", ["e"], 450);
  await waitForLocalRoomVisible("05g_secret_wall_opened", "room_c_secret_study");
  await waitForUiSettle(1800);
  await shot("06_secret_study_entered_stable");
  await state("06_secret_study_entered_stable");

  await send("07_chemical_notes", "阅读化学残页。", {
    settleMs: 1400,
    expectState: (st) => flags(st).act3_chemical_notes_seen === true
      && flags(st).act3_diary_context_gathered === true,
  });
  await send("08_iron_key_sketch", "阅读重铁钥匙草图。", {
    settleMs: 1400,
    expectState: (st) => flags(st).act3_key_sketch_seen === true
      && flags(st).act3_heavy_key_hint_known === true,
  });
  await send("09_diary_truth_memory", "阅读日记。", {
    settleMs: 1600,
    expectState: (st) => flags(st).act3_diary_read === true
      && flags(st).act3_diary_decoded === true
      && flags(st).act3_gribbo_potion_truth_known === true,
  });
  await send("10_loot_lab_key", "搜刮 study_chest，拿走 lab_key。", {
    settleMs: 1300,
    expectState: (st) => hasItem(st, "lab_key"),
  });

  await send("10b_move_back_to_lab_door", "靠近 B-D 实验室重门。", { settleMs: 900 });
  await send("11_open_lab_door", "用 lab_key 打开 door_b_to_d。", {
    settleMs: 1600,
    expectState: (st) => isOpenDoor(st, "door_b_to_d")
      && flags(st).act4_boss_room_entered === true
      && hasVisibleRoom(st, "room_d_lab"),
  });
  await send("11b_enter_lab", "走进实验室。", {
    settleMs: 1200,
    expectState: (st) => Number(st.party_status?.player?.x) === 5
      && Number(st.party_status?.player?.y) === 7,
  });

  await send("12_boss_strategy_split", "我们怎么处理 Gribbo？", {
    settleMs: 2800,
    expectState: (st) => flags(st).act4_gribbo_confrontation_started === true
      || flags(st).act4_boss_room_entered === true,
  });
  await page.waitForTimeout(2600);
  await shot("13_boss_strategy_rotation");
  await state("13_boss_strategy_rotation");

  await send(
    "14_truth_negotiation_key",
    "我知道药剂对你做了什么。你不是守卫，你是实验品。把钥匙给我，我们带你离开。",
    {
      settleMs: 1800,
      expectState: (st) => flags(st).act4_heavy_iron_key_obtained === true
        && hasItem(st, "heavy_iron_key"),
    },
  );
  await send("15_move_final_exit", "移动到 17,4。", {
    settleMs: 1200,
    expectState: (st) => Number(st.party_status?.player?.x) === 17
      && Number(st.party_status?.player?.y) === 4,
  });
  await send("16_final_exit_demo_cleared", "用 heavy_iron_key 打开 heavy_oak_door_1。", {
    settleMs: 1800,
    expectState: (st) => st.demo_cleared === true
      && flags(st).act4_final_exit_opened === true,
  });

  const finalState = await state("final");
  await fs.writeFile(`${outDir}/recording_url.txt`, `${url}\n`);
  console.log(JSON.stringify({
    outDir,
    sessionId,
    capture: {
      width: captureWidth,
      height: captureHeight,
      deviceScaleFactor,
      recordVideo: shouldRecordVideo,
    },
    demo_cleared: finalState.demo_cleared,
    player: finalState.party_status?.player,
    flags: {
      act3_secret_study_entered: finalState.flags?.act3_secret_study_entered,
      act3_chemical_notes_seen: finalState.flags?.act3_chemical_notes_seen,
      act3_diary_decoded: finalState.flags?.act3_diary_decoded,
      act4_boss_room_entered: finalState.flags?.act4_boss_room_entered,
      act4_gribbo_confrontation_started: finalState.flags?.act4_gribbo_confrontation_started,
      act4_heavy_iron_key_obtained: finalState.flags?.act4_heavy_iron_key_obtained,
      act4_final_exit_opened: finalState.flags?.act4_final_exit_opened,
    },
    visible_rooms: finalState.map_data?.visible_rooms,
  }, null, 2));
} catch (error) {
  await shot("failure_last_frame").catch(() => {});
  throw error;
} finally {
  const video = page.video();
  await context.close();
  if (shouldRecordVideo && video) {
    const videoPath = await video.path().catch(() => null);
    if (videoPath) {
      await fs.writeFile(`${outDir}/raw_video_path.txt`, `${videoPath}\n`);
    }
  }
  await browser.close();
}
