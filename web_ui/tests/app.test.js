const fs = require("fs");
const path = require("path");

const INDEX_HTML_PATH = path.resolve(__dirname, "../index.html");
const APP_JS_PATH = path.resolve(__dirname, "../app.js");
const NECRO_META_PATH = path.resolve(__dirname, "../necromancer-meta.js");
const TILED_ADAPTER_PATH = path.resolve(__dirname, "../tiled-adapter.js");
const UI_EVENT_ADAPTER_PATH = path.resolve(__dirname, "../ui-event-adapter.js");
const DIRECTOR_TRACE_PATH = path.resolve(__dirname, "../director-trace.js");
const INPUT_CONTROLLER_PATH = path.resolve(__dirname, "../input-controller.js");
const HUD_RENDERERS_PATH = path.resolve(__dirname, "../hud-renderers.js");
const REAL_MAP_JSON_PATH = path.resolve(__dirname, "../assets/maps/necromancer_lab.json");

function extractBodyMarkup(htmlText) {
  const match = String(htmlText).match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  if (!match) {
    throw new Error("index.html missing <body> content");
  }
  return match[1].replace(/<script[\s\S]*?<\/script>/gi, "");
}

function mountIndexBody() {
  const source = fs.readFileSync(INDEX_HTML_PATH, "utf8");
  document.body.innerHTML = extractBodyMarkup(source);
}

function mockResponse(payload, { ok = true, status = 200 } = {}) {
  return Promise.resolve({
    ok,
    status,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  });
}

async function flushAsync() {
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function loadNewModules() {
  jest.isolateModules(() => { require(NECRO_META_PATH); });
  jest.isolateModules(() => { require(TILED_ADAPTER_PATH); });
  jest.isolateModules(() => { require(UI_EVENT_ADAPTER_PATH); });
  jest.isolateModules(() => { require(DIRECTOR_TRACE_PATH); });
  jest.isolateModules(() => { require(INPUT_CONTROLLER_PATH); });
  jest.isolateModules(() => { require(HUD_RENDERERS_PATH); });
}

async function bootAppForTest(url = "http://localhost/?qa_test=1") {
  window.history.replaceState({}, "", url);
  window.__BG3_ENABLE_TEST_API__ = true;
  window.BG3TacticalMap = {
    update: jest.fn(),
    resize: jest.fn(),
    movePlayerLocal: jest.fn(),
    getPlayerGridPosition: jest.fn().mockReturnValue({ x: 2, y: 2 }),
    drawLoSBlockerOverlay: jest.fn(),
    clearLoSBlockerOverlay: jest.fn(),
  };
  if (typeof window.requestAnimationFrame !== "function") {
    window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  }

  loadNewModules();

  jest.isolateModules(() => {
    require(APP_JS_PATH);
  });

  const api = window.__BG3_APP_TEST_API__;
  if (!api) {
    throw new Error("window.__BG3_APP_TEST_API__ not exposed");
  }
  await api.boot();
  await flushAsync();
  return api;
}

function spyOnFetch() {
  if (typeof globalThis.fetch !== "function") {
    globalThis.fetch = () => Promise.reject(new Error("unmocked fetch"));
  }
  return jest.spyOn(globalThis, "fetch");
}

describe("web_ui/app.js UI bindings", () => {
  beforeEach(() => {
    jest.resetModules();
    delete window.BG3NecromancerMeta;
    delete window.BG3TiledAdapter;
    delete window.BG3UIEventAdapter;
    delete window.BG3DirectorTrace;
    delete window.BG3InputController;
    delete window.BG3HudRenderers;
    mountIndexBody();
  });

  afterEach(() => {
    delete window.__BG3_APP_TEST_API__;
    delete window.__BG3_ENABLE_TEST_API__;
    delete window.BG3TacticalMap;
    delete window.BG3NecromancerMeta;
    delete window.BG3TiledAdapter;
    delete window.BG3UIEventAdapter;
    delete window.BG3DirectorTrace;
    delete window.BG3InputController;
    delete window.BG3HudRenderers;
    delete window.__BG3_FORCE_REAL_MAP_LOAD__;
  });

  /* ═══════════════════════════════════════════
     EXISTING TESTS (preserved from Sprint 0)
     ═══════════════════════════════════════════ */

  test("test_xray_panel_updates", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValueOnce(
      mockResponse({
        last_node: "DM_NODE",
        entities: {
          gribbo: {
            dynamic_states: {
              patience: { current_value: 8, max_value: 20 },
            },
          },
        },
        party_status: {},
        environment_objects: {},
        combat_state: {},
        journal_events: [],
      })
    );

    const api = await bootAppForTest();
    await api.pollDialogueState();

    const dmNode = document.querySelector('li[data-node="dm_analysis"]');
    expect(dmNode).not.toBeNull();
    expect(dmNode.classList.contains("is-active")).toBe(true);

    const patienceBar = document.getElementById("patience-bar");
    expect(patienceBar.style.width).toBe("40%");

    const inspector = document.getElementById("json-inspector");
    expect(inspector.textContent).toContain('"last_node": "DM_NODE"');
    expect(inspector.textContent).toContain('"current_value": 8');

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/state?session_id="),
      expect.objectContaining({ signal: expect.any(Object) })
    );
  });

  test("test_dialogue_modal_visibility", async () => {
    const firstState = {
      active_dialogue_target: "gribbo",
      party_status: { gribbo: { name: "gribbo" } },
      environment_objects: {},
      combat_state: {},
      journal_events: ['[gribbo]: "离我远点。"'],
      responses: [],
    };
    const secondState = {
      active_dialogue_target: null,
      party_status: { gribbo: { name: "gribbo" } },
      environment_objects: {},
      combat_state: {},
      journal_events: [],
      responses: [],
    };

    spyOnFetch()
      .mockResolvedValueOnce(mockResponse(firstState))
      .mockResolvedValueOnce(mockResponse(secondState));

    const api = await bootAppForTest();

    await api.pollDialogueState();
    const overlay = document.getElementById("dialogue-overlay");
    expect(overlay.classList.contains("hidden")).toBe(false);
    const npcName = document.getElementById("dialogue-npc-name").textContent || "";
    expect(npcName.toLowerCase()).toContain("gribbo");

    await api.pollDialogueState();
    expect(overlay.classList.contains("hidden")).toBe(true);
  });

  test("test_ui_input_interception", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );

    const api = await bootAppForTest();
    api.updateDialogueOverlay({
      active_dialogue_target: "gribbo",
      party_status: { gribbo: { name: "gribbo" } },
      journal_events: ['[gribbo]: "你想干什么？"'],
    });

    const attackBtn = document.getElementById("dialogue-attack-btn");
    attackBtn.click();
    await flushAsync();

    const chatCall = fetchSpy.mock.calls.find(([url]) => String(url).includes("/api/chat"));
    expect(chatCall).toBeDefined();
    const payload = JSON.parse(chatCall[1].body);
    expect(payload.user_input).toBe("我直接拔出武器攻击！");
  });

  /* ═══════════════════════════════════════════
     SPRINT 0 TESTS
     ═══════════════════════════════════════════ */

  test("test_local_movement_no_api_call", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();
    fetchSpy.mockClear();

    if (window.BG3InputController) {
      window.BG3InputController.movePlayer(1, 0);
    }
    await flushAsync();

    const chatCalls = fetchSpy.mock.calls.filter(
      ([url]) => String(url).includes("/api/chat")
    );
    expect(chatCalls.length).toBe(0);
  });

  test("test_map_id_in_payload", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [], journal_events: [], party_status: {},
        environment_objects: {}, combat_state: {},
      })
    );
    const api = await bootAppForTest();
    fetchSpy.mockClear();
    await api.sendMessage("测试指令", null);
    await flushAsync();

    const chatCall = fetchSpy.mock.calls.find(([url]) => String(url).includes("/api/chat"));
    expect(chatCall).toBeDefined();
    const payload = JSON.parse(chatCall[1].body);
    expect(payload.map_id).toBe("necromancer_lab");
  });

  test("test_heavy_iron_key_display", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();
    expect(api.ITEM_META.heavy_iron_key).toBeDefined();
    expect(api.ITEM_META.heavy_iron_key.label).toBe("沉重铁钥匙");
  });

  test("test_los_blocked_event_dom", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();

    if (window.BG3HudRenderers) {
      window.BG3HudRenderers.showLoSBlockedOverlay({ blockedTiles: [] });
    }
    await flushAsync();

    const container = document.getElementById("toast-container");
    expect(container).not.toBeNull();
    const toasts = container.querySelectorAll(".hud-toast");
    expect(toasts.length).toBeGreaterThanOrEqual(1);
    const losToast = Array.from(toasts).find((t) => t.textContent.includes("视线"));
    expect(losToast).toBeDefined();
  });

  test("test_director_trace_idle_by_default", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();

    if (window.BG3DirectorTrace) {
      expect(window.BG3DirectorTrace.getState()).toBe("idle");
    }
    const indicator = document.getElementById("director-state-indicator");
    expect(indicator).not.toBeNull();
    expect(indicator.classList.contains("director-state--idle")).toBe(true);
    expect(indicator.textContent).toContain("Idle");
  });

  /* ═══════════════════════════════════════════
     SPRINT 1 HARDENING TESTS
     ═══════════════════════════════════════════ */

  test("test_sendMessage_dispatches_ui_events", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: ["叙事回应"],
        journal_events: [],
        party_status: {},
        environment_objects: {},
        combat_state: {},
        latest_roll: { skill: "Perception", dc: 13, result: 17, success: true },
      })
    );

    const api = await bootAppForTest();
    fetchSpy.mockClear();

    await api.sendMessage("检查周围", null);
    await flushAsync();

    /* A dice card should have been spawned by the HUD renderer */
    const diceContainer = document.getElementById("dice-card-container");
    expect(diceContainer).not.toBeNull();
    const diceCards = diceContainer.querySelectorAll(".dice-card");
    expect(diceCards.length).toBeGreaterThanOrEqual(1);
  });

  test("test_init_sync_does_not_activate_director_trace", async () => {
    spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [], journal_events: [], party_status: {},
        environment_objects: {}, combat_state: {},
      })
    );

    const api = await bootAppForTest();

    /* isNarrativeRequest should return false for init_sync */
    expect(api.isNarrativeRequest("init_sync", "", "")).toBe(false);
    expect(api.isNarrativeRequest("trigger_idle_banter", "", "")).toBe(false);
    expect(api.isNarrativeRequest("ui_action_loot", "", "")).toBe(false);

    /* Director trace should still be idle after boot (which runs init_sync in non-QA) */
    if (window.BG3DirectorTrace) {
      expect(window.BG3DirectorTrace.getState()).toBe("idle");
    }
  });

  test("test_narrative_request_activates_trace", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();

    /* isNarrativeRequest should return true for narrative intents */
    expect(api.isNarrativeRequest("trigger_zone", "", "")).toBe(true);
    expect(api.isNarrativeRequest("", "我检查箱子", "")).toBe(true);
    expect(api.isNarrativeRequest("dialogue", "", "interaction")).toBe(true);
    expect(api.isNarrativeRequest("companion_interrupt", "", "")).toBe(true);
  });

  test("test_blocked_by_creates_los_event", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();

    /* Extract events from a response with blocked_by field */
    const events = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: [],
      party_status: {},
      blocked_by: [{ x: 5, y: 3 }, { x: 5, y: 4 }],
    });

    const losEvents = events.filter((e) => e.type === "line_of_sight_blocked");
    expect(losEvents.length).toBeGreaterThanOrEqual(1);
    expect(losEvents[0].blockedTiles.length).toBe(2);
    expect(losEvents[0].blocked_by).toEqual([{ x: 5, y: 3 }, { x: 5, y: 4 }]);
  });

  test("test_latest_roll_raw_roll_compat", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();

    /* Variant: result.raw_roll / is_success */
    const events1 = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: [],
      party_status: {},
      latest_roll: { result: { raw_roll: 14, dc: 13, is_success: true }, skill: "Stealth" },
    });
    const roll1 = events1.find((e) => e.type === "roll_result");
    expect(roll1).toBeDefined();
    expect(roll1.roll).toBe(14);
    expect(roll1.dc).toBe(13);
    expect(roll1.success).toBe(true);

    /* Variant: rolls array */
    const events2 = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: [],
      party_status: {},
      latest_roll: { rolls: [18], dc: 15, is_success: true },
    });
    const roll2 = events2.find((e) => e.type === "roll_result");
    expect(roll2).toBeDefined();
    expect(roll2.roll).toBe(18);
  });

  test("test_tiled_objectgroup_parsing", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();

    /* Construct a minimal Tiled JSON with objectgroup layers */
    const tiledJson = {
      width: 10,
      height: 10,
      tilewidth: 32,
      tileheight: 32,
      layers: [
        {
          name: "triggers",
          type: "objectgroup",
          objects: [
            { name: "trap_zone_1", type: "trigger", x: 96, y: 64, width: 64, height: 32 },
          ],
        },
        {
          name: "objects",
          type: "objectgroup",
          objects: [
            { name: "chest_1", type: "chest", x: 192, y: 32, width: 32, height: 32 },
            { name: "player_start", type: "player_start", x: 64, y: 64, width: 32, height: 32 },
          ],
        },
        {
          name: "spawns",
          type: "objectgroup",
          objects: [
            {
              name: "goblin_1",
              type: "spawn",
              x: 160, y: 128,
              width: 32, height: 32,
              properties: [
                { name: "faction", value: "hostile" },
              ],
            },
          ],
        },
      ],
    };

    const result = window.BG3TiledAdapter.normalizeTiledMap(tiledJson);

    /* Triggers */
    expect(result.triggers.length).toBe(1);
    expect(result.triggers[0].id).toBe("trap_zone_1");
    expect(result.triggers[0].x).toBe(3); // 96/32
    expect(result.triggers[0].y).toBe(2); // 64/32
    expect(result.triggers[0].w).toBe(2); // 64/32

    /* Interactables: chest remains present (spawn NPC may also be interactable) */
    expect(result.interactables.length).toBeGreaterThanOrEqual(1);
    const chest = result.interactables.find((it) => it.id === "chest_1");
    expect(chest).toBeDefined();
    expect(chest.type).toBe("chest");

    /* Player start */
    expect(result.playerStart.x).toBe(2); // 64/32
    expect(result.playerStart.y).toBe(2); // 64/32

    /* Spawns */
    expect(result.spawns.length).toBe(1);
    expect(result.spawns[0].id).toBe("goblin_1");
    expect(result.spawns[0].faction).toBe("hostile");
  });

  test("test_real_map_json_contract_25x25_with_625_cells", () => {
    const raw = fs.readFileSync(REAL_MAP_JSON_PATH, "utf8");
    const map = JSON.parse(raw);
    expect(map.width).toBe(25);
    expect(map.height).toBe(25);

    const collision = map.layers.find((layer) => layer.name === "collision");
    const los = map.layers.find((layer) => layer.name === "los_blockers");
    const ground = map.layers.find((layer) => layer.name === "ground_types");

    expect(collision.data.length).toBe(625);
    expect(los.data.length).toBe(625);
    expect(ground.data.length).toBe(625);
  });

  test("test_real_map_json_entities_and_trigger_contract", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();

    const raw = fs.readFileSync(REAL_MAP_JSON_PATH, "utf8");
    const map = JSON.parse(raw);
    const result = window.BG3TiledAdapter.normalizeTiledMap(map);

    expect(result.width).toBe(25);
    expect(result.height).toBe(25);
    expect(result.playerStart.x).toBe(4);
    expect(result.playerStart.y).toBe(18);

    const interactableIds = result.interactables.map((item) => item.id);
    expect(interactableIds).toContain("gribbo");
    expect(interactableIds).toContain("necromancer_diary");
    expect(interactableIds).toContain("chest_1");
    expect(interactableIds).toContain("heavy_oak_door_1");

    const spawnIds = result.spawns.map((spawn) => spawn.id);
    expect(spawnIds).toContain("gribbo");

    const corridor = result.triggers.find((trigger) => trigger.id === "act1_corridor_approach");
    expect(corridor).toBeDefined();

    const poisonTrap = result.triggers.find((trigger) => trigger.id === "poison_trap_1");
    expect(poisonTrap).toBeDefined();
    expect(poisonTrap.data.alias_id).toBe("gas_trap_1");
  });

  test("test_load_map_by_id_fallback_is_observable", async () => {
    spyOnFetch().mockRejectedValueOnce(new Error("offline"));
    loadNewModules();
    const result = await window.BG3TiledAdapter.loadMapById("necromancer_lab");
    expect(result.source).toBe("fixture");
    expect(result.reason).toBe("error");
    expect(result.map.width).toBeGreaterThan(0);
  });

  test("test_app_marks_map_source_and_qa_warning_on_real_map_fallback", async () => {
    window.__BG3_FORCE_REAL_MAP_LOAD__ = true;
    const fetchSpy = spyOnFetch().mockImplementation((url) => {
      if (String(url).includes("assets/maps/necromancer_lab.json")) {
        return Promise.reject(new Error("offline"));
      }
      return mockResponse({});
    });

    await bootAppForTest("http://localhost/?qa_test=1&qa_force_map=1");
    await flushAsync();

    const host = document.getElementById("map-container");
    expect(host.dataset.mapSource).toBe("fixture");
    expect(host.dataset.mapFallbackReason).toBe("error");

    const toastContainer = document.getElementById("toast-container");
    const warningToast = Array.from(toastContainer.querySelectorAll(".hud-toast"))
      .find((item) => item.textContent.includes("地图资产加载失败"));
    expect(warningToast).toBeDefined();
    expect(fetchSpy).toHaveBeenCalled();
  });

  test("test_session_id_from_url", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();
    /* Default session_id when no URL param is set (qa_test=1 doesn't set session_id) */
    expect(api.SESSION_ID).toBe("necromancer_lab_demo");
  });

  test("test_trigger_once_dedup", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();
    /* Switch to fake timers AFTER boot to avoid blocking async */
    jest.useFakeTimers();

    /* Set up a map with a trigger at (3,2) */
    const triggerCallback = jest.fn();
    const testMap = {
      width: 10, height: 10,
      collision: Array.from({ length: 10 }, () => Array(10).fill(false)),
      losBlockers: Array.from({ length: 10 }, () => Array(10).fill(false)),
      triggers: [{ id: "test_trap", x: 3, y: 2, w: 1, h: 1, type: "trigger", data: {} }],
      interactables: [],
      spawns: [],
    };

    window.BG3InputController.init({
      normalizedMap: testMap,
      playerStart: { x: 2, y: 2 },
      onNarrativeTrigger: triggerCallback,
    });

    /* Move into trigger zone */
    window.BG3InputController.movePlayer(1, 0); // now at 3,2 → trigger fires
    expect(triggerCallback).toHaveBeenCalledTimes(1);

    /* Stay on trigger, try to move again — cooldown + dedup means no re-fire */
    jest.advanceTimersByTime(200);
    window.BG3InputController.movePlayer(0, 0); // stays at 3,2

    /* Move out */
    jest.advanceTimersByTime(200);
    window.BG3InputController.movePlayer(-1, 0); // back to 2,2 — exits trigger zone

    /* Move back in — should fire again because player left and re-entered */
    jest.advanceTimersByTime(200);
    window.BG3InputController.movePlayer(1, 0);  // back to 3,2
    expect(triggerCallback).toHaveBeenCalledTimes(2);

    jest.useRealTimers();
  });

  /* ═══════════════════════════════════════════
     P1 FIX TESTS
     ═══════════════════════════════════════════ */

  test("test_poll_dialogue_dispatches_ui_events", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();

    /* Set previous party state to detect affection delta */
    api.state.partyStatus = { astarion: { affection: 0 } };

    /* Now mock the next fetch (pollDialogueState calls /api/state) */
    fetchSpy.mockResolvedValueOnce(mockResponse({
      journal_events: ["视线被阻挡 NO_LOS"],
      party_status: { astarion: { affection: 5 } },
      environment_objects: {},
      combat_state: {},
    }));

    await api.pollDialogueState();
    await flushAsync();

    /* LoS blocked toast should have been created */
    const container = document.getElementById("toast-container");
    expect(container).not.toBeNull();
    const toasts = container.querySelectorAll(".hud-toast");
    expect(toasts.length).toBeGreaterThanOrEqual(1);
  });

  test("test_fixture_has_act1_corridor_trigger", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();

    const m = window.BG3TiledAdapter.normalizeTiledMap(null);
    /* At least one trigger should exist (act1_corridor_approach) */
    expect(m.triggers.length).toBeGreaterThanOrEqual(1);
    const act1 = m.triggers.find((t) => t.id === "act1_corridor_approach");
    expect(act1).toBeDefined();
    expect(act1.type).toBe("narrative_trigger");
    expect(act1.y).toBe(3);
  });

  test("test_trap_type_recognized_as_trigger", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();

    /* Build a YAML map with a trap obstacle */
    const trapMap = {
      map_id: "test_trap_map",
      dimensions: [5, 5],
      player_start: [0, 0],
      grid: [
        ". . . . .",
        ". . . . .",
        ". . . . .",
        ". . . . .",
        ". . . . .",
      ],
      obstacles: [
        {
          type: "trap",
          entity_id: "poison_trap",
          name: "毒气陷阱",
          coordinates: [[2, 2]],
          blocks_movement: false,
          blocks_los: false,
        },
      ],
      environment_objects: [],
      spawns: [],
    };

    const result = window.BG3TiledAdapter.normalizeTiledMap(trapMap);
    const trapTrigger = result.triggers.find((t) => t.id === "poison_trap");
    expect(trapTrigger).toBeDefined();
    expect(trapTrigger.x).toBe(2);
    expect(trapTrigger.y).toBe(2);
  });

  test("test_qa_no_idle_disables_idle_banter_post", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest("http://localhost/?qa_no_idle=1&qa_test=1");

    jest.useFakeTimers();
    fetchSpy.mockClear();
    await api.sendMessage("检查周围", null);
    jest.advanceTimersByTime(35000);
    jest.useRealTimers();

    const chatCalls = fetchSpy.mock.calls
      .filter(([url]) => String(url).includes("/api/chat"))
      .map(([, req]) => JSON.parse(req.body));
    expect(chatCalls.length).toBe(1);
    expect(chatCalls[0].intent).toBe("chat");
    expect(chatCalls.some((payload) => payload.intent === "trigger_idle_banter")).toBe(false);
  });

  test("test_interactable_type_maps_to_structured_intent_target", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    await bootAppForTest();
    fetchSpy.mockClear();

    const baseMap = {
      width: 20,
      height: 14,
      collision: Array.from({ length: 14 }, () => Array(20).fill(false)),
      losBlockers: Array.from({ length: 14 }, () => Array(20).fill(false)),
      triggers: [],
      spawns: [],
      interactables: [],
    };

    window.BG3InputController.setMap({
      ...baseMap,
      interactables: [{ id: "necromancer_diary", type: "readable", x: 3, y: 2, name: "日记" }],
    });
    window.BG3InputController.setPlayerPosition(2, 2);
    window.BG3InputController.interact();
    await flushAsync();

    window.BG3InputController.setMap({
      ...baseMap,
      interactables: [{ id: "gribbo", type: "npc", x: 3, y: 2, name: "Gribbo" }],
    });
    window.BG3InputController.setPlayerPosition(2, 2);
    window.BG3InputController.interact();
    await flushAsync();

    window.BG3InputController.setMap({
      ...baseMap,
      interactables: [{ id: "heavy_oak_door_1", type: "door", x: 3, y: 2, name: "大门" }],
    });
    window.BG3InputController.setPlayerPosition(2, 2);
    window.BG3InputController.interact();
    await flushAsync();

    window.BG3InputController.setMap({
      ...baseMap,
      interactables: [{ id: "chest_1", type: "chest", x: 3, y: 2, name: "箱子" }],
    });
    window.BG3InputController.setPlayerPosition(2, 2);
    window.BG3InputController.interact();
    await flushAsync();

    const chatPayloads = fetchSpy.mock.calls
      .filter(([url]) => String(url).includes("/api/chat"))
      .map(([, req]) => JSON.parse(req.body));

    expect(chatPayloads[0].intent).toBe("READ");
    expect(chatPayloads[0].target).toBe("necromancer_diary");

    expect(chatPayloads[1].intent).toBe("CHAT");
    expect(chatPayloads[1].target).toBe("gribbo");

    expect(chatPayloads[2].intent).toBe("INTERACT");
    expect(chatPayloads[2].target).toBe("heavy_oak_door_1");

    expect(chatPayloads[3].intent).toBe("ui_action_loot");
    expect(chatPayloads[3].target).toBe("chest_1");
  });

  test("test_read_diary_then_plain_act3_text_does_not_reuse_read_unknown", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest();
    fetchSpy.mockClear();

    await api.sendMessage("", "READ", null, {
      target: "necromancer_diary",
      source: "interaction",
    });
    await api.sendMessage("阿斯代伦说得对，我们一起嘲笑 Gribbo。", null);
    await flushAsync();

    const chatPayloads = fetchSpy.mock.calls
      .filter(([url]) => String(url).includes("/api/chat"))
      .map(([, req]) => JSON.parse(req.body));

    expect(chatPayloads[0].intent).toBe("READ");
    expect(chatPayloads[0].target).toBe("necromancer_diary");
    expect(chatPayloads[1].intent).toBe("CHAT");
    expect(chatPayloads[1].target).toBe("gribbo");
    expect(chatPayloads[1].target).not.toBe("unknown");
  });

  test("test_active_dialogue_target_gribbo_forces_chat_target_on_plain_text", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest();
    fetchSpy.mockClear();
    api.state.activeDialogueTarget = "gribbo";

    await api.sendMessage("我支持阿斯代伦。", null);
    await flushAsync();

    const chatCall = fetchSpy.mock.calls.find(([url]) => String(url).includes("/api/chat"));
    const payload = JSON.parse(chatCall[1].body);
    expect(payload.intent).toBe("CHAT");
    expect(payload.target).toBe("gribbo");
    expect(payload.source).toBe("dialogue_input");
  });

  test("test_interaction_hint_target_matches_e_payload_target", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    await bootAppForTest();
    fetchSpy.mockClear();

    const baseMap = {
      width: 20,
      height: 14,
      collision: Array.from({ length: 14 }, () => Array(20).fill(false)),
      losBlockers: Array.from({ length: 14 }, () => Array(20).fill(false)),
      triggers: [],
      spawns: [],
      interactables: [],
    };

    window.BG3InputController.setMap({
      ...baseMap,
      interactables: [{ id: "heavy_oak_door_1", type: "door", x: 3, y: 2, name: "大门" }],
    });
    window.BG3InputController.setPlayerPosition(2, 2);
    window.BG3InputController.updateHint();

    const hintText = String(document.getElementById("interaction-hint").textContent || "");
    expect(hintText).toContain("heavy_oak_door_1");

    window.BG3InputController.interact();
    await flushAsync();

    const chatCall = fetchSpy.mock.calls.find(([url]) => String(url).includes("/api/chat"));
    const payload = JSON.parse(chatCall[1].body);
    expect(payload.intent).toBe("INTERACT");
    expect(payload.target).toBe("heavy_oak_door_1");
  });

  test("test_hidden_trap_does_not_steal_e_interaction_target", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    await bootAppForTest();
    fetchSpy.mockClear();

    const baseMap = {
      width: 20,
      height: 14,
      collision: Array.from({ length: 14 }, () => Array(20).fill(false)),
      losBlockers: Array.from({ length: 14 }, () => Array(20).fill(false)),
      triggers: [],
      spawns: [],
      interactables: [],
    };

    window.BG3InputController.setMap({
      ...baseMap,
      interactables: [
        { id: "gas_trap_1", type: "trap", x: 3, y: 2, name: "毒气陷阱", is_hidden: true },
        { id: "chest_1", type: "chest", x: 2, y: 3, name: "箱子" },
      ],
    });
    window.BG3InputController.setPlayerPosition(2, 2);
    window.BG3InputController.interact();
    await flushAsync();

    const chatCall = fetchSpy.mock.calls.find(([url]) => String(url).includes("/api/chat"));
    const payload = JSON.parse(chatCall[1].body);
    expect(payload.intent).toBe("ui_action_loot");
    expect(payload.target).toBe("chest_1");

    fetchSpy.mockClear();
    window.BG3InputController.setMap({
      ...baseMap,
      interactables: [{ id: "gas_trap_1", type: "trap", x: 3, y: 2, name: "毒气陷阱", is_hidden: true }],
    });
    window.BG3InputController.setPlayerPosition(2, 2);
    window.BG3InputController.interact();
    await flushAsync();

    const callsAfterHiddenTrapOnly = fetchSpy.mock.calls.filter(([url]) => String(url).includes("/api/chat"));
    expect(callsAfterHiddenTrapOnly.length).toBe(0);
  });

  test("test_door_natural_language_normalizes_to_interact_target", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest();
    fetchSpy.mockClear();

    const commands = [
      "打开门",
      "开门",
      "使用钥匙打开门",
      "用 heavy_iron_key 打开门",
      "检查 heavy_oak_door_1",
    ];

    for (const command of commands) {
      await api.sendMessage(command, null);
    }
    await flushAsync();

    const payloads = fetchSpy.mock.calls
      .filter(([url]) => String(url).includes("/api/chat"))
      .map(([, req]) => JSON.parse(req.body));
    expect(payloads.length).toBe(commands.length);
    payloads.forEach((payload) => {
      expect(payload.intent).toBe("INTERACT");
      expect(payload.target).toBe("heavy_oak_door_1");
    });
  });

  test("test_text_input_open_door_payload_normalizes_to_interact_target", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {
          heavy_oak_door_1: { id: "heavy_oak_door_1", type: "door", status: "closed" },
        },
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest();
    fetchSpy.mockClear();

    api.els.userInput.value = "打开门";
    api.els.sendBtn.click();
    await flushAsync();

    const chatCall = fetchSpy.mock.calls.find(([url]) => String(url).includes("/api/chat"));
    expect(chatCall).toBeDefined();
    const payload = JSON.parse(chatCall[1].body);
    expect(payload.source).toBe("text_input");
    expect(payload.intent).toBe("INTERACT");
    expect(payload.target).toBe("heavy_oak_door_1");
  });

  test("test_text_input_open_door_with_key_payload_normalizes_to_interact_target", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "测试场景",
        party_status: {},
        environment_objects: {
          heavy_oak_door_1: { id: "heavy_oak_door_1", type: "door", status: "closed" },
        },
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest();
    fetchSpy.mockClear();

    api.els.userInput.value = "使用钥匙打开门";
    api.els.sendBtn.click();
    await flushAsync();

    const chatCall = fetchSpy.mock.calls.find(([url]) => String(url).includes("/api/chat"));
    expect(chatCall).toBeDefined();
    const payload = JSON.parse(chatCall[1].body);
    expect(payload.source).toBe("text_input");
    expect(payload.intent).toBe("INTERACT");
    expect(payload.target).toBe("heavy_oak_door_1");
  });
});
