/**
 * demo-script-runner.js
 * Showcase-only scripted path through necromancer_lab.
 * Exposed on window.BG3DemoScriptRunner.
 */
(() => {
  "use strict";

  const DEFAULT_DELAY_MS = 1050;

  function safeObj(value) {
    return value && typeof value === "object" ? value : {};
  }

  function wait(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, Math.max(0, Number(ms) || 0)));
  }

  function createRunner(api, options = {}) {
    const app = safeObj(api);
    const opts = safeObj(options);
    let running = false;
    let stopped = false;
    let index = 0;
    let currentPromise = null;
    const delayMs = Number(opts.delayMs) || DEFAULT_DELAY_MS;

    const steps = [
      {
        id: "new_session",
        title: "Act 0 — Fresh Session",
        summary: "Initialize a clean necromancer_lab timeline.",
        run: async () => {
          if (typeof app.startNewTimeline === "function") await app.startNewTimeline();
        },
      },
      {
        id: "reveal_b",
        title: "Act 1 — Room Reveal",
        summary: "Open A-B door and expose visibleRooms diff.",
        run: async () => {
          if (typeof app.runShowcaseLocalStep === "function") {
            app.runShowcaseLocalStep("qa_open door_a_to_b", { title: "Act 1 — Room Reveal" });
          }
        },
      },
      {
        id: "act1_perception",
        title: "Act 1 — Trap Sense",
        summary: "Trigger perception, dice card, trap highlight, and Director Trace.",
        run: async () => {
          if (typeof app.runShowcaseLocalStep === "function") {
            app.runShowcaseLocalStep("qa_perception", { title: "Act 1 — Trap Sense" });
          }
          if (typeof app.sendMessage === "function") {
            await app.sendMessage("我谨慎进入毒气走廊，观察地面与墙缝。", "trigger_zone", null, {
              target: "act1_corridor_approach",
              source: "trigger_zone",
              skipIdleReset: true,
            });
          }
        },
      },
      {
        id: "secret_study",
        title: "Act 1.5 — Secret Study",
        summary: "Discover and open B-C secret door.",
        run: async () => {
          if (typeof app.runShowcaseLocalStep === "function") {
            app.runShowcaseLocalStep("qa_open door_b_to_c", { title: "Act 1.5 — Secret Study" });
          }
        },
      },
      {
        id: "read_diary",
        title: "Act 2 — ActorView Memory",
        summary: "Read necromancer_diary and show memory isolation plus diff.",
        run: async () => {
          if (typeof app.sendMessage === "function") {
            await app.sendMessage("用奥术知识阅读 necromancer_diary。", "READ", null, {
              target: "necromancer_diary",
              source: "interaction",
              skipIdleReset: true,
            });
          }
        },
      },
      {
        id: "loot_study_chest",
        title: "Act 2.5 — Study Chest Loot",
        summary: "Loot study_chest and show item transfer through EventDrain.",
        run: async () => {
          if (typeof app.sendMessage === "function") {
            await app.sendMessage("我要搜刮 study_chest", "ui_action_loot", "player", {
              target: "chest_1",
              source: "ui_click",
              skipIdleReset: true,
            });
          }
        },
      },
      {
        id: "open_lab",
        title: "Act 3 — Lab Door",
        summary: "Open B-D door with lab_key and reveal Gribbo chamber.",
        run: async () => {
          if (typeof app.runShowcaseLocalStep === "function") {
            app.runShowcaseLocalStep("qa_open door_b_to_d", { title: "Act 3 — Lab Door" });
          }
        },
      },
      {
        id: "gribbo_start",
        title: "Act 3 — Party Turn Coordinator",
        summary: "Start Gribbo dialogue.",
        run: async () => {
          if (typeof app.sendMessage === "function") {
            await app.sendMessage("我想和 Gribbo 谈谈。", "CHAT", null, {
              target: "gribbo",
              source: "interaction",
              skipIdleReset: true,
            });
          }
        },
      },
      {
        id: "side_astarion",
        title: "Act 3 — Astarion Branch",
        summary: "Choose side_with_astarion and expose affection/combat/hostility diffs.",
        run: async () => {
          if (typeof app.sendMessage === "function") {
            await app.sendMessage("side_with_astarion：阿斯代伦说得对，我们一起嘲笑 Gribbo。", "CHAT", null, {
              target: "gribbo",
              source: "dialogue_input",
              skipIdleReset: true,
            });
          }
        },
      },
      {
        id: "loot_gribbo_key",
        title: "Act 4 — EventDrain Key Transfer",
        summary: "Loot heavy_iron_key from Gribbo.",
        run: async () => {
          if (typeof app.sendMessage === "function") {
            await app.sendMessage("我确认 heavy_iron_key 已经入包，准备撤离。", "chat", null, {
              source: "text_input",
              skipIdleReset: true,
            });
          }
        },
      },
      {
        id: "exit",
        title: "Act 4 — Demo Cleared",
        summary: "Open exit_door and show completion banner.",
        run: async () => {
          if (typeof app.sendMessage === "function") {
            await app.sendMessage("移动到 17,4", "MOVE", null, {
              target: "17,4",
              source: "text_input",
              skipIdleReset: true,
            });
            await app.sendMessage("用 heavy_iron_key 打开 heavy_oak_door_1。", "INTERACT", null, {
              target: "heavy_oak_door_1",
              source: "interaction",
              skipIdleReset: true,
            });
            if (typeof app.completeShowcaseLocally === "function") {
              app.completeShowcaseLocally("exit_door_showcase");
            }
          }
        },
      },
    ];

    function setAct(step) {
      if (window.BG3HudRenderers && typeof window.BG3HudRenderers.updateActProgress === "function") {
        const actMatch = String(step.title || "").match(/Act\s+(\d+)/i);
        window.BG3HudRenderers.updateActProgress(actMatch ? Number(actMatch[1]) : 1, step.summary || step.title || "");
      }
      if (typeof opts.onStep === "function") opts.onStep(step, index);
    }

    async function run() {
      if (running) return currentPromise;
      running = true;
      stopped = false;
      index = 0;
      currentPromise = (async () => {
        try {
          while (index < steps.length && !stopped) {
            const step = steps[index];
            setAct(step);
            await step.run();
            index += 1;
            if (!stopped && index < steps.length) await wait(delayMs);
          }
        } finally {
          running = false;
          if (typeof opts.onDone === "function") opts.onDone({ stopped, index });
        }
        return { stopped, index };
      })();
      return currentPromise;
    }

    function stop() {
      stopped = true;
      running = false;
      if (typeof opts.onStop === "function") opts.onStop({ index });
    }

    function isRunning() {
      return running && !stopped;
    }

    return Object.freeze({ run, stop, isRunning, steps, getIndex: () => index });
  }

  window.BG3DemoScriptRunner = Object.freeze({ createRunner, wait });
})();
