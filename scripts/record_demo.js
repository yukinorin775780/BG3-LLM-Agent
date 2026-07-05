/**
 * Demo Video Recording — Uses showcase demo-script-runner for reliable flow.
 * Target: ~4 min at 1920×1080 with burnt-in English subtitles.
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const NOW = new Date();
const TS = [NOW.getFullYear(), String(NOW.getMonth()+1).padStart(2,'0'), String(NOW.getDate()).padStart(2,'0')].join('');
const OUT_DIR = path.resolve(__dirname, '..', 'artifacts', 'demo_recording', `demo_v4_${TS}`);
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

// 15s between steps × 13 delays = 195s + step execution time ≈ 3.5-4 min
const STEP_DELAY_MS = 15000;
const SESSION = `demo_v4_${TS}`;
const DEMO_URL = `http://127.0.0.1:8000/web_ui/?session_id=${SESSION}&map_id=necromancer_lab&qa_showcase=1&qa_no_idle=1&qa_showcase_step_ms=${STEP_DELAY_MS}`;

console.log('=== Demo V4 Recording ===');
console.log('Session:', SESSION);
console.log('Step delay:', STEP_DELAY_MS + 'ms');
console.log('Output:', OUT_DIR);

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: OUT_DIR, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', err => errors.push(err.message));

  // Load
  console.log('[1] Loading...');
  await page.goto(DEMO_URL, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(4000);

  // Wait for demo runner to initialize
  await page.waitForFunction(() => window.BG3DemoScriptRunner, { timeout: 15000 });
  await page.waitForTimeout(2000);

  // Collapse Director panel
  await page.evaluate(() => {
    const btn = document.getElementById('xray-toggle-btn');
    if (btn && btn.getAttribute('aria-expanded') === 'true') btn.click();
  });
  await page.waitForTimeout(1000);

  // Click Run to start demo-script-runner
  console.log('[2] Starting demo script runner...');
  const clicked = await page.evaluate(() => {
    const btn = document.getElementById('run-demo-script-btn');
    if (btn && !btn.disabled) { btn.click(); return true; }
    return false;
  });
  console.log('  Run clicked:', clicked);
  if (!clicked) { console.log('FATAL: No run button'); await browser.close(); return; }

  // Monitor demo progress by polling the status element
  console.log('[3] Waiting for demo completion...');
  const startTime = Date.now();
  let lastStatus = '';
  const maxWaitMs = 600000; // 10 min max

  while (Date.now() - startTime < maxWaitMs) {
    await page.waitForTimeout(2000);
    const status = await page.evaluate(() => {
      const el = document.getElementById('demo-script-status');
      if (!el) return null;
      return el.textContent || '';
    }).catch(() => null);

    if (status !== lastStatus) {
      console.log('  Status:', status);
      lastStatus = status;
    }

    // Check completion
    if (status && (status.includes('complete') || status.includes('stopped'))) {
      console.log('  Demo runner finished!');
      break;
    }

    // Check demo_cleared banner
    const cleared = await page.evaluate(() => {
      return !!document.querySelector('.demo-cleared--visible');
    }).catch(() => false);
    if (cleared) {
      console.log('  Demo cleared banner detected!');
      break;
    }

    // Safety: if we haven't seen a status update in 4 min, the runner might be stuck
    if (status && status.includes('step') && Date.now() - startTime > 240000) {
      const stepMatch = status.match(/step (\d+)/);
      if (stepMatch && parseInt(stepMatch[1]) < 3) {
        console.log('  Runner appears stuck at early step, breaking.');
        break;
      }
    }
  }

  // Final verification
  const final = await page.evaluate(() => ({
    cleared: !!document.querySelector('.demo-cleared--visible'),
    status: document.getElementById('demo-script-status')?.textContent || 'none',
    act: document.getElementById('act-title')?.textContent || '',
  }));
  console.log('[4] Final:', JSON.stringify(final));

  // Wait for banner animation
  await page.waitForTimeout(6000);

  console.log('[5] Stopping recording...');
  await context.close();
  await browser.close();

  // Process video
  const videos = fs.readdirSync(OUT_DIR).filter(f => f.endsWith('.webm'));
  if (!videos.length) { console.log('No video! Errors:', errors); return; }

  const raw = path.join(OUT_DIR, 'raw_recording.webm');
  fs.renameSync(path.join(OUT_DIR, videos[0]), raw);

  const { execSync } = require('child_process');

  // Convert to MP4
  const mp4 = path.join(OUT_DIR, 'final_demo.mp4');
  console.log('Converting to MP4...');
  execSync(`ffmpeg -y -i "${raw}" -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p -movflags +faststart "${mp4}"`, { stdio: 'inherit', timeout: 180000 });

  const dur = parseFloat(execSync(`ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "${mp4}"`).toString().trim());
  console.log(`Duration: ${dur.toFixed(1)}s`);

  // Verify backend state
  try {
    const resp = JSON.parse(execSync(`curl -s "http://127.0.0.1:8000/api/state?session_id=${SESSION}&map_id=necromancer_lab"`).toString());
    console.log(`Backend: demo_cleared=${resp.demo_cleared} key=${resp.player_inventory?.heavy_iron_key || 0}`);
  } catch(e) {}

  // Generate and burn subtitles
  if (dur > 30) {
    const srtPath = path.join(OUT_DIR, 'subtitles.srt');
    generateSubtitles(srtPath, dur);
    console.log('Burning subtitles...');
    burnSubtitles(mp4, srtPath, path.join(OUT_DIR, 'final_demo_subtitled.mp4'));
    const sz = fs.statSync(path.join(OUT_DIR, 'final_demo_subtitled.mp4')).size;
    console.log(`Done! ${(sz/1024/1024).toFixed(1)}MB, ${dur.toFixed(0)}s`);
  }

  if (errors.length) console.log('Page errors:', errors.slice(0, 3));
  console.log('Output:', OUT_DIR);
})();

function generateSubtitles(outPath, durationSec) {
  const fmt = (s) => { const m = Math.floor(s/60); const ss = Math.floor(s%60); return `0${m}:${String(ss).padStart(2,'0')}`; };
  const total = Math.max(durationSec || 240, 240);
  const beats = [
    [0, 5, 'BG3 LLM Agent — A Playable AI-Driven Dungeon Encounter'],
    [5, 18, 'Act 1: The party wakes in a sealed necromancer\'s lab.\nWASD movement and companions follow locally.'],
    [18, 42, 'Act 2 — Poison Corridor: Astarion\'s perception check\nreveals a hidden gas trap. Enhanced D20 dice card\nwith glow animation shows check, roll, DC, and result.'],
    [42, 68, 'Fail-Forward: Locked B-D door → failed lockpick\n→ cracked wall reveals Secret Study entrance.'],
    [68, 135, 'Act 3 — Secret Study: Reading the Necromancer\'s Diary\nunlocks information leverage. Memory isolation\nensures each companion remembers differently.'],
    [135, 162, 'Tool Calling: LLM invokes check_target_inventory\nvia ReAct loop. Director Trace highlights tool_call node.'],
    [162, 188, 'Affection Baseline: Companion affection levels\ndisplayed before confronting Gribbo.'],
    [188, 222, 'Gribbo Boss Encounter: Three companions propose\ncompeting strategies driven by personality + affection.\nLLM-driven NPC with scoped ActorView.'],
    [222, 250, 'Affection Changes: Choosing Astarion triggers\ngreen/red delta chips. Diary truth = encounter leverage.\nAstarion ↑ / Shadowheart ↓ / Lae\'zel ↑'],
    [250, total, 'Final Exit: heavy_iron_key opens the door.\ndemo_cleared=true. Full agent stack exercised.\nLangGraph · FastAPI · ChromaDB · Phaser 3'],
  ];
  let srt = '';
  beats.forEach((b, i) => {
    srt += `${i+1}\n00:${fmt(b[0])},000 --> 00:${fmt(b[1])},000\n${b[2]}\n\n`;
  });
  fs.writeFileSync(outPath, srt);
}

function burnSubtitles(mp4Path, srtPath, outPath) {
  const font = '/System/Library/Fonts/Helvetica.ttc';
  const srtContent = fs.readFileSync(srtPath, 'utf8');
  const blocks = srtContent.trim().split('\n\n');
  const dts = [];
  blocks.forEach(block => {
    const lines = block.trim().split('\n');
    if (lines.length < 3) return;
    const m = lines[1].match(/(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)/);
    if (!m) return;
    const ss = parseInt(m[1])*3600 + parseInt(m[2])*60 + parseInt(m[3]) + parseInt(m[4])/1000;
    const es = parseInt(m[5])*3600 + parseInt(m[6])*60 + parseInt(m[7]) + parseInt(m[8])/1000;
    const text = lines.slice(2).join('\\n').replace(/'/g, "'\\\\''").replace(/:/g, '\\:').replace(/%/g, '\\\\%');
    const yOff = text.includes('\\n') ? 140 : 125;
    dts.push(`drawtext=fontfile=${font}:fontsize=28:text='${text}':fontcolor=white:borderw=3:bordercolor=black@0.8:x=(w-text_w)/2:y=h-${yOff}:enable='between(t,${ss},${es})'`);
  });
  if (dts.length) {
    const { execSync } = require('child_process');
    execSync(`ffmpeg -y -i "${mp4Path}" -vf "${dts.join(',')}" -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p -movflags +faststart "${outPath}"`, { stdio: 'inherit', timeout: 300000 });
  }
}
