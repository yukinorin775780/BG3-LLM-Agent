/**
 * memory-showcase.js — Cross-Session Memory Demo
 *
 * Demonstrates that NPCs remember information from a previous session.
 * Activated when URL contains ?memory_demo=1
 *
 * Flow:
 *   Session A — Read Necromancer Diary → NPC memories are stored
 *   Session B — New session, NPC recalls diary knowledge from Session A
 *
 * Exposed on window.BG3MemoryShowcase.
 */
(() => {
  "use strict";

  const STATE_URL = "/api/state";
  const CHAT_URL = "/api/chat";
  const MAP_ID = "necromancer_lab";
  const MEMORY_SESSION_A = "memory_demo_a";
  const MEMORY_SESSION_B = "memory_demo_b";

  let panel = null;
  let running = false;

  function safeObj(v) { return v && typeof v === "object" ? v : {}; }
  function safeArr(v) { return Array.isArray(v) ? v : []; }

  function log(level, msg) {
    console.log("[MemoryDemo] " + msg);
    if (panel) {
      const line = document.createElement("div");
      line.className = "memory-demo-log memory-demo-log--" + level;
      line.textContent = msg;
      const logEl = panel.querySelector(".memory-demo-log-body");
      if (logEl) logEl.appendChild(line);
      if (logEl) logEl.scrollTop = logEl.scrollHeight;
    }
  }

  async function createPanel() {
    if (document.getElementById("memory-demo-panel")) return;

    panel = document.createElement("div");
    panel.id = "memory-demo-panel";
    panel.className = "memory-demo-panel";
    panel.innerHTML =
      '<div class="memory-demo-header">' +
        '<h2>🧠 Cross-Session Memory Demo</h2>' +
        '<p>Demonstrates that NPC companions remember information across browser sessions via ChromaDB-backed MemoryService.</p>' +
      '</div>' +
      '<div class="memory-demo-columns">' +
        '<div class="memory-demo-col" id="memory-col-a">' +
          '<h3>📝 Session A <small>memory_demo_a</small></h3>' +
          '<div class="memory-demo-response" id="memory-response-a"><em>Waiting...</em></div>' +
        '</div>' +
        '<div class="memory-demo-col" id="memory-col-b">' +
          '<h3>🔄 Session B <small>memory_demo_b</small></h3>' +
          '<div class="memory-demo-response" id="memory-response-b"><em>Waiting for Session A to complete...</em></div>' +
        '</div>' +
      '</div>' +
      '<div class="memory-demo-actions">' +
        '<button type="button" id="memory-demo-run-btn" class="memory-demo-btn memory-demo-btn--run">▶ Run Memory Demo</button>' +
        '<button type="button" id="memory-demo-reset-btn" class="memory-demo-btn">↺ Reset</button>' +
      '</div>' +
      '<details class="memory-demo-log-details">' +
        '<summary>Debug Log</summary>' +
        '<div class="memory-demo-log-body"></div>' +
      '</details>';

    document.body.appendChild(panel);

    document.getElementById("memory-demo-run-btn").addEventListener("click", () => runMemoryDemo());
    document.getElementById("memory-demo-reset-btn").addEventListener("click", () => resetMemoryDemo());
  }

  async function fetchState(sessionId) {
    const url = STATE_URL + "?session_id=" + encodeURIComponent(sessionId) + "&map_id=" + encodeURIComponent(MAP_ID);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("State fetch failed: " + resp.status);
    return resp.json();
  }

  async function sendChat(userInput, sessionId, opts = {}) {
    const payload = {
      user_input: userInput,
      session_id: sessionId,
      map_id: MAP_ID,
      source: safeObj(opts).source || "text_input",
      target: safeObj(opts).target || "",
      intent: safeObj(opts).intent || null,
      intent_context: safeObj(opts).intent_context || null,
    };
    const resp = await fetch(CHAT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error("Chat failed: " + resp.status);
    return resp.json();
  }

  function extractMemories(data) {
    const memories = [];
    // Check actor_runtime_state for memory notes
    const ars = safeObj(data.game_state || data).actor_runtime_state || {};
    Object.entries(ars).forEach(([actorId, runtime]) => {
      safeArr(safeObj(runtime).memory_notes || safeObj(runtime).memories).forEach((note) => {
        const text = typeof note === "string" ? note : (safeObj(note).text || safeObj(note).note || "");
        if (text) memories.push({ actor: actorId, text: text });
      });
    });
    // Also check journal events for memory-related lines
    safeArr(data.journal_events).forEach((line) => {
      const s = String(line || "");
      if (/memory|记忆/.test(s)) memories.push({ actor: "journal", text: s });
    });
    return memories;
  }

  function displayResponse(colId, data, memories) {
    const col = document.getElementById(colId);
    if (!col) return;
    const responseEl = col.querySelector(".memory-demo-response");
    if (!responseEl) return;

    let html = "";

    // Show NPC responses
    safeArr(data.responses).forEach((r) => {
      html += '<div class="memory-demo-bubble"><strong>' +
        escapeHtml(String(r.speaker || "npc")) + ':</strong> ' +
        escapeHtml(String(r.text || "")) + '</div>';
    });

    // Show journal events
    safeArr(data.journal_events).slice(0, 5).forEach((line) => {
      html += '<div class="memory-demo-journal">📋 ' + escapeHtml(String(line || "")) + '</div>';
    });

    // Show memories
    if (memories && memories.length > 0) {
      html += '<div class="memory-demo-memories"><h4>🧠 Stored Memories</h4>';
      memories.forEach((m) => {
        html += '<div class="memory-demo-memory-item"><em>' +
          escapeHtml(String(m.actor)) + ':</em> ' + escapeHtml(String(m.text)) + '</div>';
      });
      html += '</div>';
    }

    if (!html) html = '<em>No response data</em>';
    responseEl.innerHTML = html;
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = String(s || "");
    return div.innerHTML;
  }

  async function runMemoryDemo() {
    if (running) return;
    running = true;
    const runBtn = document.getElementById("memory-demo-run-btn");
    if (runBtn) runBtn.disabled = true;

    try {
      // === Session A: Read the diary, create memories ===
      log("info", "=== Session A: Creating memories... ===");
      displayResponse("memory-col-a", { responses: [{ speaker: "system", text: "Initializing session..." }] }, []);

      // Step A1: Initialize
      log("info", "A1: Initializing session...");
      await fetchState(MEMORY_SESSION_A);

      // Step A2: Send initial message to load the game state
      log("info", "A2: Sending initial exploration...");
      let data = await sendChat("我环顾四周，确认队伍状态。", MEMORY_SESSION_A);
      displayResponse("memory-col-a", data, extractMemories(data));
      log("info", "A2: " + safeArr(data.responses).length + " responses, " + safeArr(data.journal_events).length + " journal events");

      // Step A3: Open door to corridor
      log("info", "A3: Opening door to corridor...");
      data = await sendChat("打开通往毒气走廊的门。", MEMORY_SESSION_A);

      // Step A4: Read the diary (this creates the main memory)
      log("info", "A4: Reading Necromancer Diary (memory creation)...");
      data = await sendChat("用奥术知识阅读 necromancer_diary，仔细研究内容。", MEMORY_SESSION_A, {
        target: "necromancer_diary",
        source: "interaction",
      });
      const sessionAMemories = extractMemories(data);
      displayResponse("memory-col-a", data, sessionAMemories);
      log("info", "A4: " + sessionAMemories.length + " memories created in Session A");

      if (sessionAMemories.length === 0) {
        log("warn", "⚠ No memories extracted from Session A. The backend may not have created memory records yet.");
        // Try alternative: read chemical notes too
        log("info", "A4b: Trying chemical_notes as alternative memory source...");
        data = await sendChat("阅读 chemical_notes 上的内容。", MEMORY_SESSION_A, {
          target: "chemical_notes",
          source: "interaction",
        });
        const altMemories = extractMemories(data);
        displayResponse("memory-col-a", data, altMemories);
      }

      // === Session B: New session, recall memories ===
      log("info", "=== Session B: Recalling memories from Session A... ===");
      displayResponse("memory-col-b", { responses: [{ speaker: "system", text: "Starting new session with fresh browser state..." }] }, []);

      // Step B1: Initialize new session
      log("info", "B1: Initializing new session...");
      await fetchState(MEMORY_SESSION_B);

      // Step B2: Send message that should trigger memory retrieval
      log("info", "B2: Sending memory-trigger query...");
      data = await sendChat(
        "影心，你还记得之前我们在那个秘密书房里发现了什么关于死灵法师的事情吗？",
        MEMORY_SESSION_B,
        { source: "text_input" }
      );
      const sessionBMemories = extractMemories(data);
      displayResponse("memory-col-b", data, sessionBMemories);
      log("info", "B2: " + sessionBMemories.length + " memories visible in Session B");

      // Compare
      log("info", "=== Demo Complete ===");
      if (sessionAMemories.length > 0 && sessionBMemories.length > 0) {
        log("success", "✅ Cross-session memory working! " + sessionAMemories.length + " → " + sessionBMemories.length);
      } else if (sessionAMemories.length > 0) {
        log("warn", "⚠ Session A produced " + sessionAMemories.length + " memories, but Session B has " + sessionBMemories.length);
      } else {
        log("info", "ℹ Memory demo completed. Check responses above for memory references.");
      }
    } catch (err) {
      log("error", "Demo failed: " + (err && err.message || String(err)));
    } finally {
      running = false;
      if (runBtn) runBtn.disabled = false;
    }
  }

  function resetMemoryDemo() {
    ["memory-col-a", "memory-col-b"].forEach((colId) => {
      const col = document.getElementById(colId);
      if (col) {
        const el = col.querySelector(".memory-demo-response");
        if (el) el.innerHTML = "<em>Reset. Click 'Run Memory Demo' to start.</em>";
      }
    });
    const logEl = panel ? panel.querySelector(".memory-demo-log-body") : null;
    if (logEl) logEl.innerHTML = "";
    log("info", "Reset complete.");
  }

  function init() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("memory_demo") !== "1") return;
    log("info", "Memory Demo mode activated");
    // Wait for DOM ready
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => createPanel());
    } else {
      createPanel();
    }
  }

  window.BG3MemoryShowcase = Object.freeze({ init, runMemoryDemo, resetMemoryDemo });

  // Auto-init
  init();
})();
