/**
 * Phase 3 — Demo Video Recording V3 (Extended)
 * Manual step-by-step with longer pauses for cinematic pacing.
 * Target: 3-5 minutes at 1920×1080.
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const NOW = new Date();
const TS = [
  NOW.getFullYear(),
  String(NOW.getMonth() + 1).padStart(2, '0'),
  String(NOW.getDate()).padStart(2, '0'),
].join('');
const TAG_NAME = `demo-v3-${TS}`;
const OUT_DIR = path.resolve(__dirname, '..', 'artifacts', 'demo_recording', `demo_v3_${TS}`);
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

const SESSION_ID = `demo_v3_${TS}`;
const DEMO_URL = `http://127.0.0.1:8000/web_ui/?session_id=${SESSION_ID}&map_id=necromancer_lab&qa_showcase=1&qa_no_idle=1`;

console.log('=== BG3 Demo V3 Recording (Extended) ===');
console.log('Tag:', TAG_NAME);
console.log('Output:', OUT_DIR);

(async () => {
  // NOTE: headless: false is REQUIRED for proper Phaser 3 WebGL rendering.
  // Headless Chromium uses software WebGL which produces a blank/black canvas.
  // This means demo recording needs a display (macOS WindowServer or Xvfb).
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    recordVideo: { dir: OUT_DIR, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();

  // Load
  console.log('[1] Loading...');
  await page.goto(DEMO_URL, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(3000); // Title card pause

  // Collapse Director panel
  await page.evaluate(() => {
    const btn = document.getElementById('xray-toggle-btn');
    if (btn && btn.getAttribute('aria-expanded') === 'true') btn.click();
  });
  await page.waitForTimeout(1000);

  // Each step: type, wait, send, wait for full HUD animations to play out.
  // Target total runtime: ~4.5 minutes (270s)
  const STEPS = [
    { text: '我环顾四周，确认队伍状态。', label: 'Act 1 — Wake Up', preWait: 800, postWait: 15000 },
    { text: '打开通往毒气走廊的门。', label: 'Act 1 — Open Door to Corridor', preWait: 800, postWait: 15000 },
    { text: '我谨慎进入毒气走廊，观察地面与墙缝。', label: 'Act 2 — Trap Perception Check', preWait: 1000, postWait: 20000 },
    { text: '搜索墙壁，寻找隐藏通道。', label: 'Act 2 — Discover Secret Entrance', preWait: 800, postWait: 18000 },
    { text: '用奥术知识阅读 necromancer_diary。', label: 'Act 3 — Read Necromancer Diary', preWait: 1000, postWait: 22000 },
    { text: '我要搜刮 study_chest。', label: 'Act 3 — Loot Study Chest', preWait: 800, postWait: 18000 },
    { text: '用 lab_key 打开通往实验室的重门。', label: 'Act 3 — Enter Gribbo Lab', preWait: 1000, postWait: 20000 },
    { text: '阿斯代伦，帮我看看 chest_1 里面还有没有什么遗漏的东西？', label: 'Act 3 — Tool Calling: check_target_inventory', preWait: 1200, postWait: 22000 },
    { text: '我想和 Gribbo 谈谈。', label: 'Act 4 — Confront Gribbo', preWait: 1500, postWait: 25000 },
    { text: '我知道药水对你做了什么。你不是守卫，你是实验品。把钥匙给我。', label: 'Act 4 — Diary Truth Negotiation', preWait: 1500, postWait: 25000 },
    { text: '用 heavy_iron_key 打开 heavy_oak_door_1。', label: 'Final — Open Exit Door', preWait: 1500, postWait: 20000 },
  ];

  for (let i = 0; i < STEPS.length; i++) {
    const step = STEPS[i];
    console.log(`  [${i + 1}/${STEPS.length}] ${step.label}`);

    // Type the command
    await page.evaluate((text) => {
      const input = document.getElementById('dock-input');
      if (input) {
        input.value = text;
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }, step.text);
    await page.waitForTimeout(step.preWait || 800);

    // Click send
    await page.evaluate(() => {
      const btn = document.getElementById('dock-send-btn');
      if (btn && !btn.disabled) btn.click();
    });

    // Wait for HUD animations to play out fully
    await page.waitForTimeout(step.postWait);

    // Extra dramatic pauses between acts
    if (i === 1) await page.waitForTimeout(5000);  // Act 1 → Act 2
    if (i === 3) await page.waitForTimeout(6000);  // Act 2 → Act 3
    if (i === 6) await page.waitForTimeout(7000);  // Act 3 → Act 4
    if (i === 8) await page.waitForTimeout(5000);  // Pre-final dramatic pause
  }

  // Final pause for demo cleared banner
  console.log('  Waiting for demo cleared banner...');
  await page.waitForTimeout(5000);

  console.log('Stopping recording...');
  await context.close();
  await browser.close();

  // Process video
  const videoFiles = fs.readdirSync(OUT_DIR).filter(f => f.endsWith('.webm'));
  if (videoFiles.length > 0) {
    const src = path.join(OUT_DIR, videoFiles[0]);
    const dst = path.join(OUT_DIR, 'raw_recording.webm');
    if (src !== dst) fs.renameSync(src, dst);

    console.log('Converting to MP4...');
    const { execSync } = require('child_process');
    try {
      execSync(
        `ffmpeg -i "${dst}" -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p -movflags +faststart "${path.join(OUT_DIR, 'final_demo.mp4')}"`,
        { stdio: 'inherit', timeout: 120000 }
      );
    } catch (e) { /* webm still available */ }
  }

  generateArtifacts(OUT_DIR);
  console.log('\nDone! Tag:', TAG_NAME);
  console.log('Output:', OUT_DIR);
})();

function generateArtifacts(outDir) {
  const srt = `1
00:00:00,000 --> 00:00:05,000
BG3 LLM Agent — A Playable AI-Driven Dungeon Encounter
Necromancer Lab V3

2
00:00:05,000 --> 00:00:18,000
Act 1: The party wakes in a sealed necromancer's lab.
WASD movement and companion following are 100% local — no API calls.

3
00:00:18,000 --> 00:00:35,000
Act 2 — Poison Corridor: Astarion's perception check reveals a hidden gas trap.
The UI shows companion bark, trap marker, and D20 dice card.

4
00:00:35,000 --> 00:01:00,000
Fail-Forward Routing: The B-D lab door is locked.
A failed lockpick reveals a cracked wall instead of blocking progress.

5
00:01:00,000 --> 00:02:00,000
Act 3 — Secret Study: The party discovers a hidden side room.
Reading Chemical Notes, Iron Key Sketch, and the Necromancer's Diary
unlocks information leverage for the upcoming boss encounter.

6
00:02:00,000 --> 00:02:30,000
The Study Chest yields a lab_key. All item transfers pass through
deterministic EventDrain pipelines — LLM output never directly mutates world state.

7
00:02:30,000 --> 00:03:30,000
Act 4 — Gribbo Boss Encounter:
LLM-driven NPC with scoped ActorView perception.
Three companions propose competing strategies based on their personalities and agendas.

8
00:03:30,000 --> 00:04:30,000
Diary truth functions as encounter leverage.
The heavy iron key is transferred through the runtime state path.
State-driven branching: reading the diary earlier changes this conversation.

9
00:04:30,000 --> 00:05:00,000
Final Exit: heavy_iron_key opens the final door. demo_cleared=true.
The full agent stack is exercised end-to-end.

10
00:05:00,000 --> 00:05:15,000
Built with LangGraph · FastAPI · ChromaDB · Phaser 3
github.com/yukinorin775780/BG3-LLM-Agent
`;
  fs.writeFileSync(path.join(outDir, 'subtitles.srt'), srt);

  const md = `# Demo Shot List — V3

| # | Act | Est. Time | Content |
|---|-----|-----------|---------|
| 1 | Title | 0:00–0:05 | Title card |
| 2 | Act 1 | 0:05–0:18 | Safe room, party wake, door opening |
| 3 | Act 2 | 0:18–0:35 | Poison Corridor, trap perception, dice card |
| 4 | Act 2 Fail | 0:35–1:00 | Locked door, fail-forward to secret wall |
| 5 | Act 3 | 1:00–2:00 | Secret Study, diary, memory isolation |
| 6 | Act 3 | 2:00–2:30 | Loot chest, EventDrain key transfer |
| 7 | Act 4 | 2:30–3:30 | Gribbo boss dialogue, companion strategies |
| 8 | Act 4 | 3:30–4:30 | Diary truth negotiation, key transfer |
| 9 | Final | 4:30–5:00 | Exit door, demo_cleared |
| 10 | Outro | 5:00–5:15 | Tech stack, GitHub link |

Target: ~5 minutes · 1920×1080 · English subtitles
`;
  fs.writeFileSync(path.join(outDir, 'shotlist.md'), md);
  console.log('Artifacts generated.');
}
