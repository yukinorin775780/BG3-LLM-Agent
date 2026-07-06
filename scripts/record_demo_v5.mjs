#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const now = new Date();
const stamp = process.env.BG3_DEMO_STAMP
  || now.toISOString().replace(/[-:]/g, "").replace(/\..*/, "");
const outDir = path.resolve(
  process.env.BG3_DEMO_OUT || path.join(repoRoot, "artifacts", "demo_recording", `demo_v5_${stamp}`),
);
const sessionId = process.env.BG3_DEMO_SESSION || `demo_v5_${stamp}`;
const baseUrl = (process.env.BG3_DEMO_BASE || "http://127.0.0.1:8010").replace(/\/+$/, "");
const captureScript = path.join(repoRoot, "scripts", "acceptance", "run_fresh_visual_capture.mjs");

const requiredScreens = [
  "03_astarion_perception.png",
  "04_astarion_disarm.png",
  "05b_locked_lab_door_inspect.png",
  "05c_lockpick_fail_hint.png",
  "06_secret_study_entered_stable.png",
  "07_chemical_notes.png",
  "08_iron_key_sketch.png",
  "09_diary_truth_memory.png",
  "10_loot_lab_key.png",
  "11b_enter_lab.png",
  "13_boss_strategy_rotation.png",
  "14_truth_negotiation_key.png",
  "16_final_exit_demo_cleared.png",
];

const requiredToolNames = [
  "query_party_memory",
  "check_target_inventory",
  "roll_skill_check",
  "transfer_item",
];

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    stdio: options.stdio || "inherit",
    env: { ...process.env, ...options.env },
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit ${result.status}`);
  }
  return result;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function assert(condition, message, details = {}) {
  if (!condition) {
    const error = new Error(message);
    error.details = details;
    throw error;
  }
}

function hasItem(state, itemId) {
  return Number(state?.player_inventory?.[itemId] || state?.game_state?.player_inventory?.[itemId] || 0) > 0;
}

function flags(state) {
  return state && typeof state.flags === "object" ? state.flags : {};
}

function formatSrtTime(seconds) {
  const ms = Math.max(0, Math.round(seconds * 1000));
  const hh = Math.floor(ms / 3600000);
  const mm = Math.floor((ms % 3600000) / 60000);
  const ss = Math.floor((ms % 60000) / 1000);
  const mmm = ms % 1000;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")},${String(mmm).padStart(3, "0")}`;
}

function writeSubtitles(filePath, duration) {
  const beats = [
    [0.00, 0.08, "Not a chatbot: a playable LLM-driven RPG runtime."],
    [0.08, 0.14, "Local WASD movement keeps ordinary walking out of the narrative backend."],
    [0.14, 0.22, "Act 2: Astarion rolls Perception, reveals the hidden gas trap, and interrupts safely."],
    [0.22, 0.30, "Natural language routes to Astarion's actor runtime and disables the trap."],
    [0.30, 0.38, "The locked B-D lab door exposes the key requirement and high-DC lockpick route."],
    [0.38, 0.46, "Fail-forward: a failed lockpick reveals the cracked wall to the Secret Study."],
    [0.46, 0.60, "Act 3: notes, key sketch, diary, and study chest build memory and negotiation leverage."],
    [0.60, 0.72, "The lab key sends the party back to the door instead of teleporting to Act 4."],
    [0.72, 0.82, "Act 4: Gribbo, poison tank, final exit, and party strategy split are readable."],
    [0.82, 0.92, "Backend tool trace: memory query, inventory check, skill roll, and item transfer."],
    [0.92, 1.00, "The heavy iron key opens the final exit. demo_cleared=true."],
  ];
  let content = "";
  beats.forEach(([startRatio, endRatio, text], index) => {
    const start = Math.min(duration - 0.1, duration * startRatio);
    const end = Math.max(start + 0.5, Math.min(duration, duration * endRatio));
    content += `${index + 1}\n${formatSrtTime(start)} --> ${formatSrtTime(end)}\n${text}\n\n`;
  });
  fs.writeFileSync(filePath, content, "utf8");
}

function validateSrt(filePath) {
  const text = fs.readFileSync(filePath, "utf8");
  let lastEnd = -1;
  for (const block of text.trim().split(/\n\s*\n/)) {
    const match = block.match(/(\d\d):(\d\d):(\d\d),(\d\d\d)\s+-->\s+(\d\d):(\d\d):(\d\d),(\d\d\d)/);
    if (!match) continue;
    const values = match.slice(1).map(Number);
    const start = values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000;
    const end = values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000;
    assert(end > start, "Subtitle cue ends before it starts", { block });
    assert(start >= lastEnd, "Subtitle cues overlap or move backwards", { block });
    lastEnd = end;
  }
}

function ffprobeDuration(filePath) {
  const result = spawnSync("ffprobe", [
    "-v", "quiet",
    "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1",
    filePath,
  ], { encoding: "utf8" });
  assert(result.status === 0, "ffprobe failed", { stderr: result.stderr });
  return Number(result.stdout.trim());
}

function convertVideo(rawPath, mp4Path) {
  run("ffmpeg", [
    "-y",
    "-i", rawPath,
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "20",
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    mp4Path,
  ]);
}

function burnSubtitles(mp4Path, srtPath, outPath) {
  run("ffmpeg", [
    "-y",
    "-i", mp4Path,
    "-vf", `subtitles=${srtPath}:force_style='Fontsize=18,Outline=2,Shadow=1,Alignment=2,MarginV=36'`,
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "20",
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    outPath,
  ]);
}

function validateArtifacts() {
  const screenshotsDir = path.join(outDir, "screenshots");
  const responsesDir = path.join(outDir, "responses");
  const finalStatePath = path.join(outDir, "final.state.json");
  const truthResponsePath = path.join(responsesDir, "14_truth_negotiation_key.response.json");

  assert(fs.existsSync(finalStatePath), "Missing final.state.json");
  assert(fs.existsSync(truthResponsePath), "Missing truth negotiation response JSON");
  for (const name of requiredScreens) {
    assert(fs.existsSync(path.join(screenshotsDir, name)), `Missing required screenshot: ${name}`);
  }

  const finalState = readJson(finalStatePath);
  const truthResponse = readJson(truthResponsePath);
  const finalFlags = flags(finalState);
  assert(finalState.demo_cleared === true, "Final state did not set demo_cleared=true");
  assert(finalFlags.act4_final_exit_opened === true, "Final exit was not opened");
  assert(hasItem(finalState, "heavy_iron_key"), "Player does not have heavy_iron_key");
  assert(hasItem(finalState, "lab_key"), "Player does not have lab_key");
  assert(finalFlags.act3_diary_decoded === true, "Act3 diary was not decoded");
  assert(finalFlags.act4_heavy_iron_key_obtained === true, "Act4 key-obtained flag missing");
  assert(!finalFlags.act2_gas_trap_triggered && !finalFlags.necromancer_lab_poison_trap_triggered, "Poison trap triggered in clean demo path");

  const toolCalls = Array.isArray(truthResponse.tool_calls) ? truthResponse.tool_calls : [];
  const toolResults = Array.isArray(truthResponse.tool_results) ? truthResponse.tool_results : [];
  const callNames = toolCalls.map((item) => item.tool_name || item.toolName);
  const resultNames = toolResults.map((item) => item.tool_name || item.toolName);
  for (const name of requiredToolNames) {
    assert(callNames.includes(name), `Missing backend tool call: ${name}`, { callNames });
    assert(resultNames.includes(name), `Missing backend tool result: ${name}`, { resultNames });
  }
  assert(toolResults.every((item) => item.success !== false), "At least one backend tool result failed", { toolResults });

  return { finalState, truthResponse, callNames, resultNames };
}

function writeReport(summary) {
  const reportPath = path.join(outDir, "acceptance_report.md");
  const content = `# Demo V5 Recording Acceptance

## Result

PASS

## Video

- Raw MP4: \`${path.join(outDir, "final_demo.mp4")}\`
- Subtitled MP4: \`${path.join(outDir, "final_demo_subtitled.mp4")}\`

## Coverage

- Act1 local WASD without narrative backend call
- Act2 Astarion Perception, safe interrupt, trap disarm
- B-D locked door, high-DC lockpick fail, cracked wall route
- Act3 Secret Study spatial entry, readable props, diary memory leverage
- Return to B-D door with lab_key, no Act3 -> Act4 teleport
- Act4 Boss Lab, strategy split, backend tool trace, key transfer
- Final exit and \`demo_cleared=true\`

## Backend Tool Trace

\`\`\`json
${JSON.stringify({
  tool_calls: summary.callNames,
  tool_results: summary.resultNames,
}, null, 2)}
\`\`\`

## Final State

\`\`\`json
${JSON.stringify({
  demo_cleared: summary.finalState.demo_cleared,
  act4_final_exit_opened: flags(summary.finalState).act4_final_exit_opened,
  heavy_iron_key: summary.finalState.player_inventory?.heavy_iron_key || 0,
  lab_key: summary.finalState.player_inventory?.lab_key || 0,
  visible_rooms: summary.finalState.map_data?.visible_rooms || [],
}, null, 2)}
\`\`\`
`;
  fs.writeFileSync(reportPath, content, "utf8");
}

console.log("=== Demo V5 Recording Gate ===");
console.log("Base:", baseUrl);
console.log("Session:", sessionId);
console.log("Output:", outDir);

fs.mkdirSync(outDir, { recursive: true });

run(process.execPath, [captureScript], {
  env: {
    BG3_CAPTURE_BASE: baseUrl,
    BG3_CAPTURE_OUT: outDir,
    BG3_CAPTURE_SESSION: sessionId,
    BG3_RECORD_VIDEO: "1",
    BG3_HEADLESS: process.env.BG3_DEMO_HEADLESS || "0",
  },
});

const rawPathFile = path.join(outDir, "raw_video_path.txt");
assert(fs.existsSync(rawPathFile), "Missing raw_video_path.txt from capture script");
const rawWebmPath = fs.readFileSync(rawPathFile, "utf8").trim();
assert(rawWebmPath && fs.existsSync(rawWebmPath), "Recorded raw video does not exist", { rawWebmPath });

const mp4Path = path.join(outDir, "final_demo.mp4");
const srtPath = path.join(outDir, "subtitles.srt");
const subtitledPath = path.join(outDir, "final_demo_subtitled.mp4");
convertVideo(rawWebmPath, mp4Path);
const duration = ffprobeDuration(mp4Path);
assert(duration > 120, "Demo video is suspiciously short", { duration });
writeSubtitles(srtPath, duration);
validateSrt(srtPath);
burnSubtitles(mp4Path, srtPath, subtitledPath);

const summary = validateArtifacts();
writeReport(summary);
console.log(JSON.stringify({
  result: "PASS",
  outDir,
  final_demo: mp4Path,
  final_demo_subtitled: subtitledPath,
  duration,
  tool_calls: summary.callNames,
}, null, 2));
