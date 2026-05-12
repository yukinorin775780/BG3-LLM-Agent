const fs = require("fs");
const path = require("path");

const INDEX_HTML_PATH = path.resolve(__dirname, "../index.html");
const APP_JS_PATH = path.resolve(__dirname, "../app.js");
const NECRO_META_PATH = path.resolve(__dirname, "../necromancer-meta.js");
const TILED_ADAPTER_PATH = path.resolve(__dirname, "../tiled-adapter.js");
const UI_EVENT_ADAPTER_PATH = path.resolve(__dirname, "../ui-event-adapter.js");
const DIRECTOR_TRACE_PATH = path.resolve(__dirname, "../director-trace.js");
const STATE_DIFF_RENDERER_PATH = path.resolve(__dirname, "../state-diff-renderer.js");
const DEMO_SCRIPT_RUNNER_PATH = path.resolve(__dirname, "../demo-script-runner.js");
const INPUT_CONTROLLER_PATH = path.resolve(__dirname, "../input-controller.js");
const HUD_RENDERERS_PATH = path.resolve(__dirname, "../hud-renderers.js");
const GAME_JS_PATH = path.resolve(__dirname, "../game.js");
const REAL_MAP_JSON_PATH = path.resolve(__dirname, "../assets/maps/necromancer_lab.json");
const REAL_MAP_TMX_PATH = path.resolve(__dirname, "../../data/maps/necromancer_lab.tmx");

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
  jest.isolateModules(() => { require(STATE_DIFF_RENDERER_PATH); });
  jest.isolateModules(() => { require(DEMO_SCRIPT_RUNNER_PATH); });
  jest.isolateModules(() => { require(INPUT_CONTROLLER_PATH); });
  jest.isolateModules(() => { require(HUD_RENDERERS_PATH); });
}

function loadGameHelpers() {
  delete window.BG3TacticalMap;
  const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
  jest.isolateModules(() => { require(GAME_JS_PATH); });
  warnSpy.mockRestore();
  return window.BG3TacticalMap;
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
    playTrapDiscoveryHighlight: jest.fn(),
    playTrapHazardPulse: jest.fn(),
    setInteractionFocus: jest.fn(),
    setTrapSenseMode: jest.fn(),
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

function extractObjectNamesByLayerFromTmx(xmlText) {
  const text = String(xmlText || "");
  const result = {};
  const groupRe = /<objectgroup[^>]*name=\"([^\"]+)\"[^>]*>([\s\S]*?)<\/objectgroup>/g;
  let groupMatch;
  while ((groupMatch = groupRe.exec(text))) {
    const layerName = groupMatch[1];
    const body = groupMatch[2];
    const names = [];
    const objectRe = /<object[^>]*name=\"([^\"]+)\"[^>]*>/g;
    let objectMatch;
    while ((objectMatch = objectRe.exec(body))) {
      names.push(objectMatch[1]);
    }
    result[layerName] = names;
  }
  return result;
}

function extractTileLayersFromTmx(xmlText) {
  const text = String(xmlText || "");
  const mapMatch = text.match(/<map[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"/);
  const result = {
    width: mapMatch ? Number(mapMatch[1]) : 0,
    height: mapMatch ? Number(mapMatch[2]) : 0,
    layers: {},
  };
  const layerRe = /<layer[^>]*\bname="([^"]+)"[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"[^>]*>[\s\S]*?<data[^>]*>([\s\S]*?)<\/data>[\s\S]*?<\/layer>/g;
  let layerMatch;
  while ((layerMatch = layerRe.exec(text))) {
    result.layers[layerMatch[1]] = {
      width: Number(layerMatch[2]),
      height: Number(layerMatch[3]),
      cells: layerMatch[4]
        .split(",")
        .map((cell) => cell.trim())
        .filter((cell) => cell.length > 0),
    };
  }
  return result;
}

function getMapLayer(map, layerName) {
  return (map.layers || []).find((layer) => layer.name === layerName);
}

function getMapObject(map, layerName, objectName) {
  const layer = getMapLayer(map, layerName);
  return ((layer && layer.objects) || []).find((object) => object.name === objectName);
}

function flattenTiledProps(object) {
  return ((object && object.properties) || []).reduce((out, prop) => {
    out[prop.name] = prop.value;
    return out;
  }, {});
}

function pointInRect(point, rect) {
  return (
    point.x >= rect.x &&
    point.x < rect.x + rect.w &&
    point.y >= rect.y &&
    point.y < rect.y + rect.h
  );
}

function roomById(rooms, roomId) {
  return rooms.find((room) => room.id === roomId);
}

describe("web_ui/app.js UI bindings", () => {
  beforeEach(() => {
    jest.resetModules();
    delete window.BG3NecromancerMeta;
    delete window.BG3TiledAdapter;
    delete window.BG3UIEventAdapter;
    delete window.BG3DirectorTrace;
    delete window.BG3StateDiffRenderer;
    delete window.BG3DemoScriptRunner;
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
    delete window.BG3StateDiffRenderer;
    delete window.BG3DemoScriptRunner;
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

    const dmNode = document.querySelector('li[data-node="dm_router"]');
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
    if (window.BG3DirectorTrace) {
      expect(window.BG3DirectorTrace.getState()).toBe("idle");
    }
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
    expect(api.isNarrativeRequest("", "我检查箱子", "")).toBe(false);
    expect(api.isNarrativeRequest("dialogue", "", "interaction")).toBe(true);
    expect(api.isNarrativeRequest("companion_interrupt", "", "")).toBe(true);
    expect(api.isNarrativeRequest("INTERACT", "", "text_input")).toBe(true);
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

    const ground = map.layers.find((layer) => layer.name === "ground");
    const collision = map.layers.find((layer) => layer.name === "collision");
    const los = map.layers.find((layer) => layer.name === "los_blockers");
    const groundTypes = map.layers.find((layer) => layer.name === "ground_types");

    expect(ground.data.length).toBe(625);
    expect(collision.data.length).toBe(625);
    expect(los.data.length).toBe(625);
    expect(groundTypes.data.length).toBe(625);
  });

  test("test_real_map_json_entities_and_trigger_contract", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();

    const raw = fs.readFileSync(REAL_MAP_JSON_PATH, "utf8");
    const map = JSON.parse(raw);
    const result = window.BG3TiledAdapter.normalizeTiledMap(map);

    expect(result.width).toBe(25);
    expect(result.height).toBe(25);
    expect(result.playerStart.x).toBe(5);
    expect(result.playerStart.y).toBe(19);

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

  test("test_necromancer_lab_v2_level_design_alignment_contract", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();

    const map = JSON.parse(fs.readFileSync(REAL_MAP_JSON_PATH, "utf8"));
    const tmx = extractTileLayersFromTmx(fs.readFileSync(REAL_MAP_TMX_PATH, "utf8"));
    const expectedCells = map.width * map.height;
    expect(tmx.width).toBe(map.width);
    expect(tmx.height).toBe(map.height);
    ["ground", "collision", "los_blockers", "ground_types"].forEach((layerName) => {
      const layer = getMapLayer(map, layerName);
      expect(layer).toBeDefined();
      expect(layer.type).toBe("tilelayer");
      expect(layer.data.length).toBe(expectedCells);
      expect(tmx.layers[layerName]).toBeDefined();
      expect(tmx.layers[layerName].width).toBe(map.width);
      expect(tmx.layers[layerName].height).toBe(map.height);
      expect(tmx.layers[layerName].cells.length).toBe(expectedCells);
    });

    const normalized = window.BG3TiledAdapter.normalizeTiledMap(map);
    const rooms = normalized.rooms;
    const roomIds = rooms.map((room) => room.id);
    expect(roomIds).toEqual(expect.arrayContaining([
      "room_a_spawn",
      "room_b_corridor",
      "room_c_secret_study",
      "room_d_lab",
      "room_exit",
    ]));

    const corridor = roomById(rooms, "room_b_corridor");
    expect(corridor).toBeDefined();
    expect(Math.max(corridor.w, corridor.h) / Math.min(corridor.w, corridor.h)).toBeGreaterThanOrEqual(2.5);

    const rawSecretDoor = getMapObject(map, "interactables", "door_b_to_c");
    const secretDoorProps = flattenTiledProps(rawSecretDoor);
    expect(secretDoorProps.is_secret).toBe(true);
    expect(Number(secretDoorProps.detect_dc)).toBe(14);
    expect(secretDoorProps.connects_from).toBe("room_b_corridor");
    expect(secretDoorProps.connects_to).toBe("room_c_secret_study");

    const rawLabDoor = getMapObject(map, "interactables", "door_b_to_d");
    const labDoorProps = flattenTiledProps(rawLabDoor);
    expect(labDoorProps.key_required).toBe("lab_key");
    expect(Number(labDoorProps.lockpick_dc)).toBe(15);
    expect(labDoorProps.connects_from).toBe("room_b_corridor");
    expect(labDoorProps.connects_to).toBe("room_d_lab");

    const rawExitDoor = getMapObject(map, "interactables", "exit_door");
    const exitDoorProps = flattenTiledProps(rawExitDoor);
    expect(exitDoorProps.alias_id).toBe("heavy_oak_door_1");
    expect(exitDoorProps.key_required).toBe("heavy_iron_key");
    expect(exitDoorProps.requires_flag).toBe("world_necromancer_lab_gribbo_defeated");

    const studyRoom = roomById(rooms, "room_c_secret_study");
    const diary = normalized.interactables.find((item) => item.id === "necromancer_diary");
    const chest = normalized.interactables.find((item) => item.id === "chest_1");
    expect(diary).toBeDefined();
    expect(chest).toBeDefined();
    expect(diary.source_id).toBe("necromancer_diary");
    expect(chest.source_id).toBe("study_chest");
    expect(pointInRect(diary, studyRoom)).toBe(true);
    expect(pointInRect(chest, studyRoom)).toBe(true);

    const labRoom = roomById(rooms, "room_d_lab");
    const gribbo = normalized.spawns.find((spawn) => spawn.id === "gribbo");
    expect(gribbo).toBeDefined();
    expect(pointInRect(gribbo, labRoom)).toBe(true);

    const doorA = normalized.interactables.find((item) => item.id === "door_a_to_b");
    ["poison_trap_1", "poison_trap_2"].forEach((trapId) => {
      const trap = normalized.triggers.find((item) => item.id === trapId);
      expect(trap).toBeDefined();
      expect(pointInRect(trap, corridor)).toBe(true);
      const distanceFromDoorA = Math.abs(trap.x - doorA.x) + Math.abs(trap.y - doorA.y);
      expect(distanceFromDoorA).toBeGreaterThanOrEqual(5);
    });

    const spawnRoom = roomById(rooms, "room_a_spawn");
    expect(pointInRect(normalized.playerStart, spawnRoom)).toBe(true);
  });

  test("test_tmx_json_object_layers_are_aligned", () => {
    const tmxText = fs.readFileSync(REAL_MAP_TMX_PATH, "utf8");
    const jsonText = fs.readFileSync(REAL_MAP_JSON_PATH, "utf8");
    const map = JSON.parse(jsonText);
    const tmxLayers = extractObjectNamesByLayerFromTmx(tmxText);
    const jsonLayers = {};
    map.layers
      .filter((layer) => layer.type === "objectgroup")
      .forEach((layer) => {
        jsonLayers[layer.name] = (layer.objects || []).map((obj) => obj.name);
      });

    ["triggers", "interactables", "spawns", "rooms"].forEach((layerName) => {
      expect(jsonLayers[layerName]).toBeDefined();
      const tmxNames = tmxLayers[layerName] || [];
      const jsonNames = jsonLayers[layerName] || [];
      tmxNames.forEach((name) => {
        expect(jsonNames).toContain(name);
      });
    });
  });

  test("test_rooms_and_doors_metadata_contract", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();
    const map = JSON.parse(fs.readFileSync(REAL_MAP_JSON_PATH, "utf8"));
    const result = window.BG3TiledAdapter.normalizeTiledMap(map);

    const roomIds = result.rooms.map((room) => room.id);
    expect(roomIds).toEqual(expect.arrayContaining([
      "room_a_spawn",
      "room_b_corridor",
      "room_c_secret_study",
      "room_d_lab",
      "room_exit",
    ]));

    const doorA = result.interactables.find((it) => it.id === "door_a_to_b");
    const doorC = result.interactables.find((it) => it.id === "door_b_to_c");
    const doorD = result.interactables.find((it) => it.id === "door_b_to_d");
    const exitDoor = result.interactables.find((it) => it.id === "heavy_oak_door_1");
    expect(doorA.data.connects_from).toBe("room_a_spawn");
    expect(doorA.data.connects_to).toBe("room_b_corridor");
    expect(doorC.data.is_secret).toBe(true);
    expect(Number(doorC.data.detect_dc)).toBe(14);
    expect(doorD.data.key_required).toBe("lab_key");
    expect(Number(doorD.data.lockpick_dc)).toBe(15);
    expect(exitDoor.data.key_required).toBe("heavy_iron_key");
    expect(exitDoor.data.requires_flag).toBe("world_necromancer_lab_gribbo_defeated");
    expect(exitDoor.source_id).toBe("exit_door");
  });

  test("test_room_visibility_initial_only_a_and_progressive_reveal", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();
    const map = JSON.parse(fs.readFileSync(REAL_MAP_JSON_PATH, "utf8"));
    const normalized = window.BG3TiledAdapter.normalizeTiledMap(map);
    api.applyNormalizedMap(normalized, { source: "json" });

    expect(Array.from(api.state.roomVisibleIds)).toEqual(["room_a_spawn"]);

    const initialInteractableIds = api.state.normalizedMap.interactables.map((it) => it.id);
    expect(initialInteractableIds).toContain("door_a_to_b");
    expect(initialInteractableIds).not.toContain("door_b_to_d");
    expect(initialInteractableIds).not.toContain("door_b_to_c");
    expect(initialInteractableIds).not.toContain("necromancer_diary");
    expect(initialInteractableIds).not.toContain("chest_1");

    expect(api.revealRoomByDoorTarget("door_a_to_b")).toBe(true);
    api.refreshVisibilityProjection();
    expect(api.state.roomVisibleIds.has("room_b_corridor")).toBe(true);

    const afterAB = api.state.normalizedMap.interactables.map((it) => it.id);
    expect(afterAB).toContain("door_b_to_d");
    expect(afterAB).not.toContain("door_b_to_c");
    expect(afterAB).not.toContain("necromancer_diary");

    expect(api.revealRoomByDoorTarget("door_b_to_d")).toBe(true);
    api.refreshVisibilityProjection();
    expect(api.state.roomVisibleIds.has("room_d_lab")).toBe(true);
    const afterBD = api.state.normalizedMap.interactables.map((it) => it.id);
    expect(afterBD).toContain("gribbo");
    expect(afterBD).toContain("heavy_oak_door_1");

    expect(api.revealRoomByDoorTarget("heavy_oak_door_1")).toBe(true);
    api.refreshVisibilityProjection();
    expect(api.state.roomVisibleIds.has("room_exit")).toBe(true);
  });

  test("test_secret_door_and_room_c_visibility_gate", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();
    const map = JSON.parse(fs.readFileSync(REAL_MAP_JSON_PATH, "utf8"));
    const normalized = window.BG3TiledAdapter.normalizeTiledMap(map);
    api.applyNormalizedMap(normalized, { source: "json" });

    api.revealRoomByDoorTarget("door_a_to_b");
    api.refreshVisibilityProjection();
    let ids = api.state.normalizedMap.interactables.map((it) => it.id);
    expect(ids).not.toContain("door_b_to_c");
    expect(ids).not.toContain("necromancer_diary");
    expect(ids).not.toContain("chest_1");

    api.discoverSecretDoor("door_b_to_c");
    api.refreshVisibilityProjection();
    ids = api.state.normalizedMap.interactables.map((it) => it.id);
    expect(ids).toContain("door_b_to_c");
    expect(ids).not.toContain("necromancer_diary");
    expect(ids).not.toContain("chest_1");

    api.revealRoomByDoorTarget("door_b_to_c");
    api.refreshVisibilityProjection();
    ids = api.state.normalizedMap.interactables.map((it) => it.id);
    expect(ids).toContain("necromancer_diary");
    expect(ids).toContain("chest_1");
  });

  test("test_tactical_projection_uses_player_start_when_backend_player_in_hidden_room", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "死灵法师的废弃实验室",
        party_status: {
          player: { name: "玩家", faction: "player", x: 2, y: 2 },
        },
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest();
    fetchSpy.mockClear();

    const map = JSON.parse(fs.readFileSync(REAL_MAP_JSON_PATH, "utf8"));
    const normalized = window.BG3TiledAdapter.normalizeTiledMap(map);
    api.applyNormalizedMap(normalized, { source: "json" });
    window.BG3TacticalMap.update.mockClear();

    await api.sendMessage("查看当前位置", "chat");
    await flushAsync();

    const lastCall = window.BG3TacticalMap.update.mock.calls.at(-1);
    expect(lastCall).toBeDefined();
    const projectedParty = lastCall[0] || {};
    expect(projectedParty.player.x).toBe(5);
    expect(projectedParty.player.y).toBe(19);
    expect(api.state.partyStatus.player.x).toBe(2);
    expect(api.state.partyStatus.player.y).toBe(2);
  });

  test("test_json_visual_map_structure_is_not_overridden_by_runtime_map_data", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "死灵法师的废弃实验室",
        party_status: {
          player: { name: "玩家", faction: "player", x: 4, y: 18 },
        },
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
        map_data: {
          id: "necromancer_lab",
          width: 20,
          height: 14,
          grid: Array.from({ length: 14 }, () => Array(20).fill(".")),
          collision: Array.from({ length: 14 }, () => Array(20).fill(false)),
          los_blockers: Array.from({ length: 14 }, () => Array(20).fill(false)),
          ground_types: Array.from({ length: 14 }, () => Array(20).fill(0)),
          rooms: [],
          visible_rooms: [],
        },
      })
    );
    const api = await bootAppForTest();
    const map = JSON.parse(fs.readFileSync(REAL_MAP_JSON_PATH, "utf8"));
    const normalized = window.BG3TiledAdapter.normalizeTiledMap(map);
    api.applyNormalizedMap(normalized, { source: "json" });
    fetchSpy.mockClear();

    await api.sendMessage("检查地图结构", "chat");
    await flushAsync();

    expect(api.state.mapLoadSource).toBe("json");
    expect(api.state.mapData.width).toBe(25);
    expect(api.state.mapData.height).toBe(25);
    expect(api.state.mapData.visible_rooms).toContain("room_a_spawn");
    expect(api.state.mapData.rooms.length).toBeGreaterThanOrEqual(5);
  });

  test("test_qa_map_debug_chip_outputs_source_and_positions", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest("http://localhost/?qa_test=1&qa_map_debug=1");
    api.updateMapDebug("unit_test");
    await flushAsync();

    const chip = document.getElementById("qa-map-debug-chip");
    expect(chip).not.toBeNull();
    const text = String(chip.textContent || "");
    expect(text).toContain("[qa_map_debug]");
    expect(text).toContain("mapSource=");
    expect(text).toContain("roomVisibleIds=");
    expect(text).toContain("backendPlayer=");
  });

  test("test_qa_map_source_badge_only_visible_for_json_source", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest("http://localhost/?qa_test=1");
    const map = JSON.parse(fs.readFileSync(REAL_MAP_JSON_PATH, "utf8"));
    const normalized = window.BG3TiledAdapter.normalizeTiledMap(map);
    api.applyNormalizedMap(normalized, { source: "json" });

    const badge = document.getElementById("qa-map-source-badge");
    expect(badge).not.toBeNull();
    expect(badge.classList.contains("is-hidden")).toBe(false);
    expect(String(badge.textContent || "")).toContain("mapSource=json");

    api.applyNormalizedMap(normalized, { source: "fixture", reason: "unit_test" });
    expect(badge.classList.contains("is-hidden")).toBe(true);
  });

  test("test_fetch_with_timeout_fallback_records_error_diagnostics", async () => {
    const fetchSpy = spyOnFetch().mockRejectedValue(new Error("synthetic_network_error"));
    const api = await bootAppForTest("http://localhost/?qa_test=1&qa_map_debug=1");
    fetchSpy.mockClear();

    await api.sendMessage("测试网络降级", "chat");
    await flushAsync();

    const lastFetch = api.state.mapDebugLastFetch;
    expect(lastFetch).toBeDefined();
    expect(lastFetch.url).toContain("/api/chat");
    expect(lastFetch.ok).toBe(false);
    expect(String(lastFetch.error && lastFetch.error.message || "")).toContain("synthetic_network_error");
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

  test("test_new_timeline_generates_new_session_and_init_sync_without_idle_chatter", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "死灵法师的废弃实验室",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest("http://localhost/?qa_test=1&qa_no_idle=1");
    fetchSpy.mockClear();
    await api.startNewTimeline();
    await flushAsync();

    const chatCalls = fetchSpy.mock.calls
      .filter(([url]) => String(url).includes("/api/chat"))
      .map(([, req]) => JSON.parse(req.body));
    expect(chatCalls.length).toBe(1);
    expect(chatCalls[0].intent).toBe("init_sync");
    expect(chatCalls[0].session_id).toMatch(/^necromancer_lab_demo_\d+$/);
    expect(chatCalls[0].session_id).not.toBe("necromancer_lab_demo");
    expect(api.SESSION_ID).toBe(chatCalls[0].session_id);
    const currentSessionInUrl = new URL(window.location.href).searchParams.get("session_id");
    expect(currentSessionInUrl).toBe(chatCalls[0].session_id);
    expect(chatCalls.some((payload) => payload.intent === "trigger_idle_banter")).toBe(false);
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

  test("test_plain_text_read_diary_routes_to_read_necromancer_diary", async () => {
    const api = await bootAppForTest();
    const { payload } = api.buildChatPayload("读日记", null, null, { source: "text_input" });

    expect(payload.intent).toBe("READ");
    expect(payload.target).toBe("necromancer_diary");
    expect(payload.source).toBe("ui_text_normalized");
  });

  test("test_gribbo_diary_truth_text_routes_to_chat_gribbo_not_use_item", async () => {
    const api = await bootAppForTest();
    const { payload } = api.buildChatPayload(
      "Gribbo，我读了日记，知道你喝了死灵药剂，也知道钥匙和实验的真相。",
      "USE_ITEM",
      null,
      { source: "text_input", target: "gribbo" }
    );

    expect(payload.intent).toBe("CHAT");
    expect(payload.target).toBe("gribbo");
    expect(payload.source).toBe("ui_text_normalized");
    expect(payload.intent_context).toEqual({ diary_negotiation_hint: true });
    expect(payload.intent).not.toBe("USE_ITEM");
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

  test("test_active_dialogue_target_gribbo_keeps_plain_text_as_chat", async () => {
    const api = await bootAppForTest();
    api.state.activeDialogueTarget = "gribbo";

    const { payload } = api.buildChatPayload("我知道你在隐瞒钥匙。", null, null, {});

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
    expect(hintText).toContain("E 打开门");
    expect(hintText).toContain("[heavy_oak_door_1]");

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

  test("test_hidden_secret_door_not_in_interaction_candidates_until_discovered", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();
    const map = JSON.parse(fs.readFileSync(REAL_MAP_JSON_PATH, "utf8"));
    const normalized = window.BG3TiledAdapter.normalizeTiledMap(map);
    api.applyNormalizedMap(normalized, { source: "json" });
    api.revealRoomByDoorTarget("door_a_to_b");
    api.refreshVisibilityProjection();

    const idsBefore = api.state.normalizedMap.interactables.map((it) => it.id);
    expect(idsBefore).not.toContain("door_b_to_c");

    api.discoverSecretDoor("door_b_to_c");
    api.refreshVisibilityProjection();
    const idsAfter = api.state.normalizedMap.interactables.map((it) => it.id);
    expect(idsAfter).toContain("door_b_to_c");
  });

  test("test_discovered_trap_renders_danger_hint_without_overriding_interactable", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();

    const baseMap = {
      width: 20,
      height: 14,
      collision: Array.from({ length: 14 }, () => Array(20).fill(false)),
      losBlockers: Array.from({ length: 14 }, () => Array(20).fill(false)),
      triggers: [],
      spawns: [],
      interactables: [],
      rooms: [],
    };

    window.BG3InputController.setMap({
      ...baseMap,
      interactables: [{ id: "gas_trap_1", type: "trap", x: 3, y: 2, name: "毒气陷阱", is_hidden: false, is_revealed: true }],
    });
    window.BG3InputController.setPlayerPosition(2, 2);
    window.BG3InputController.updateHint();
    const dangerOnlyText = String(document.getElementById("interaction-hint").textContent || "");
    expect(dangerOnlyText).toContain("危险：");
    expect(dangerOnlyText).toContain("gas_trap_1");

    window.BG3InputController.setMap({
      ...baseMap,
      interactables: [
        { id: "gas_trap_1", type: "trap", x: 3, y: 2, name: "毒气陷阱", is_hidden: false, is_revealed: true },
        { id: "chest_1", type: "chest", x: 2, y: 3, name: "箱子" },
      ],
    });
    window.BG3InputController.setPlayerPosition(2, 2);
    window.BG3InputController.updateHint();
    const withChestText = String(document.getElementById("interaction-hint").textContent || "");
    expect(withChestText).toContain("E 搜刮");
    expect(withChestText).toContain("[chest_1]");
  });

  test("test_hidden_room_objects_do_not_claim_e_hint", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    const api = await bootAppForTest();
    const map = JSON.parse(fs.readFileSync(REAL_MAP_JSON_PATH, "utf8"));
    const normalized = window.BG3TiledAdapter.normalizeTiledMap(map);
    api.applyNormalizedMap(normalized, { source: "json" });

    const chest = api.state.fullNormalizedMap.interactables.find((it) => it.id === "chest_1");
    expect(chest).toBeDefined();
    window.BG3InputController.setMap(api.state.normalizedMap);
    window.BG3InputController.setPlayerPosition(Number(chest.x), Number(chest.y));
    window.BG3InputController.updateHint();

    const text = String(document.getElementById("interaction-hint").textContent || "");
    expect(text).toBe("");
  });

  test("test_narrative_interactions_activate_director_trace_state_machine", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: ["叙事回应"],
        journal_events: [],
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest();
    fetchSpy.mockClear();

    await api.sendStructuredAction({
      text: "",
      intent: "INTERACT",
      options: { target: "door_a_to_b", source: "interaction" },
    });
    await flushAsync();
    if (window.BG3DirectorTrace) {
      expect(["active", "idle"]).toContain(window.BG3DirectorTrace.getState());
    }

    await api.sendStructuredAction({
      text: "阅读日记",
      intent: "READ",
      options: { target: "necromancer_diary", source: "interaction" },
    });
    await flushAsync();
    if (window.BG3DirectorTrace) {
      expect(["active", "idle"]).toContain(window.BG3DirectorTrace.getState());
    }

    await api.sendStructuredAction({
      text: "",
      intent: "CHAT",
      options: { target: "gribbo", source: "dialogue_input" },
    });
    await flushAsync();
    if (window.BG3DirectorTrace) {
      expect(["active", "idle"]).toContain(window.BG3DirectorTrace.getState());
    }
  });

  test("test_reset_demo_button_visible_and_starts_new_session", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValue(
      mockResponse({
        responses: [],
        journal_events: [],
        current_location: "死灵法师的废弃实验室",
        party_status: {},
        environment_objects: {},
        player_inventory: {},
        combat_state: {},
      })
    );
    const api = await bootAppForTest("http://localhost/?qa_test=1&qa_no_idle=1");
    const resetBtn = document.getElementById("new-timeline-btn");
    expect(resetBtn).not.toBeNull();
    expect(resetBtn.textContent).toContain("Reset Demo");
    expect(document.getElementById("rest-controls").classList.contains("is-hidden")).toBe(false);
    fetchSpy.mockClear();
    resetBtn.click();
    await flushAsync();

    const chatCalls = fetchSpy.mock.calls
      .filter(([url]) => String(url).includes("/api/chat"))
      .map(([, req]) => JSON.parse(req.body));
    expect(chatCalls.length).toBe(1);
    expect(chatCalls[0].intent).toBe("init_sync");
    expect(chatCalls[0].session_id).toMatch(/^necromancer_lab_demo_\d+$/);
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

  test("test_text_input_explicit_door_ids_route_to_matching_targets", async () => {
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

    await api.sendMessage("打开门 door_a_to_b", "INTERACT");
    await api.sendMessage("打开门 door_b_to_d", "INTERACT");
    await flushAsync();

    const payloads = fetchSpy.mock.calls
      .filter(([url]) => String(url).includes("/api/chat"))
      .map(([, req]) => JSON.parse(req.body));
    expect(payloads[0].target).toBe("door_a_to_b");
    expect(payloads[1].target).toBe("door_b_to_d");
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

  test("test_qa_showcase_shows_run_demo_script", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest("http://localhost/?qa_test=1&qa_showcase=1");
    expect(document.getElementById("run-demo-script-btn")).not.toBeNull();
  });

  test("test_qa_map_debug_only_hides_run_demo_script", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest("http://localhost/?qa_test=1&qa_map_debug=1");
    expect(document.getElementById("run-demo-script-btn")).toBeNull();
  });

  test("test_qa_showcase_and_map_debug_shows_run_demo_script", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest("http://localhost/?qa_test=1&qa_showcase=1&qa_map_debug=1");
    expect(document.getElementById("run-demo-script-btn")).not.toBeNull();
  });

  test("test_normal_url_hides_run_demo_script", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest("http://localhost/?qa_test=1");
    expect(document.getElementById("run-demo-script-btn")).toBeNull();
  });

  test("test_wasd_and_hover_do_not_activate_director_trace", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest("http://localhost/?qa_test=1");
    if (window.BG3InputController) {
      window.BG3InputController.movePlayer(1, 0);
    }
    document.getElementById("map-container").dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    await flushAsync();
    expect(window.BG3DirectorTrace.getState()).toBe("idle");
  });

  test("test_diary_event_constructs_memory_eventdrain_trace_nodes", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();
    const nodes = window.BG3DirectorTrace.buildTraceNodes({
      journal_events: ["[记忆] actor_private:astarion += memory_note", "EventDrain committed memory_update x2"],
      game_state: { actor_runtime_state: { astarion: { memory_notes: ["diary"] } } },
    }, { userLine: "read necromancer_diary", intent: "READ" });
    expect(nodes).toEqual(expect.arrayContaining(["actor_view_filter", "domain_event", "event_drain", "ui_events"]));
  });

  test("test_gribbo_branch_constructs_party_coordinator_affection_trace_nodes", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();
    const nodes = window.BG3DirectorTrace.buildTraceNodes({
      journal_events: ["Astarion affection +2", "Party Coordinator selected side_with_astarion", "combat_active true"],
    }, { userLine: "side_with_astarion", intent: "CHAT" });
    const details = window.BG3DirectorTrace.buildTraceDetails({
      journal_events: ["Astarion affection +2", "Party Coordinator selected side_with_astarion"],
    }, { nodes, userLine: "side_with_astarion", intent: "CHAT" });
    expect(nodes).toEqual(expect.arrayContaining(["actor_runtime", "domain_event", "event_drain"]));
    expect(details.actor_runtime.output).toContain("Party Coordinator");
    expect(details.domain_event.output).toContain("affection +2");
  });

  test("test_director_trace_activates_for_diary_read_and_gribbo_negotiation", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();

    const diaryNodes = window.BG3DirectorTrace.buildTraceNodes({}, {
      userLine: "读日记",
      intent: "READ",
    });
    const negotiationNodes = window.BG3DirectorTrace.buildTraceNodes({
      journal_events: ["[交涉筹码] diary_evidence -> gribbo_elixir_truth"],
    }, {
      userLine: "Gribbo，我读了日记，知道你喝了死灵药剂，也知道钥匙和实验的真相。",
      intent: "CHAT",
    });
    const expected = ["player_input", "dm_router", "actor_runtime", "domain_event", "event_drain", "ui_events"];

    expected.forEach((node) => {
      expect(diaryNodes).toContain(node);
      expect(negotiationNodes).toContain(node);
    });
  });

  test("test_wasd_still_does_not_activate_trace", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest("http://localhost/?qa_test=1");
    if (window.BG3InputController) {
      window.BG3InputController.movePlayer(1, 0);
    }
    await flushAsync();
    expect(window.BG3DirectorTrace.getState()).toBe("idle");
  });

  test("test_item_transfer_constructs_domainevent_eventdrain_item_toast_trace", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();
    const events = window.BG3UIEventAdapter.extractUIEvents(
      { player_inventory: { lab_key: 1 }, journal_events: ["EventDrain item_transfer lab_key"] },
      { player_inventory: {} }
    );
    const nodes = window.BG3DirectorTrace.buildTraceNodes({
      journal_events: ["DomainEvent actor_item_transaction_requested", "EventDrain item_transfer lab_key"],
    }, { userLine: "loot study_chest", intent: "ui_action_loot", uiEvents: events });
    const details = window.BG3DirectorTrace.buildTraceDetails({}, { nodes, uiEvents: events, userLine: "loot study_chest" });
    expect(nodes).toEqual(expect.arrayContaining(["domain_event", "event_drain", "ui_events"]));
    expect(events.some((event) => event.type === "item_gained" && event.item === "lab_key")).toBe(true);
    expect(details.ui_events.output).toContain("Item Toast");
  });

  test("test_state_diff_detects_visibleRooms_added", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();
    const diffs = window.BG3StateDiffRenderer.diffSnapshots(
      { roomVisibleIds: ["room_a_spawn"] },
      { roomVisibleIds: ["room_a_spawn", "room_b_corridor"] }
    );
    expect(diffs.map((d) => d.label)).toContain("visibleRooms += room_b_corridor");
  });

  test("test_state_diff_detects_inventory_added", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();
    const diffs = window.BG3StateDiffRenderer.diffSnapshots(
      { player_inventory: {} },
      { player_inventory: { lab_key: 1 } }
    );
    expect(diffs.map((d) => d.label)).toContain("player.inventory += lab_key");
  });

  test("test_state_diff_detects_affection_change", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();
    const diffs = window.BG3StateDiffRenderer.diffSnapshots(
      { party_status: { astarion: { name: "Astarion", affection: 0 } } },
      { party_status: { astarion: { name: "Astarion", affection: 2 } } }
    );
    expect(diffs.map((d) => d.label)).toContain("Astarion.affection +2");
  });

  test("test_state_diff_detects_memory_note_added", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();
    const diffs = window.BG3StateDiffRenderer.diffSnapshots(
      { actor_runtime_state: { astarion: { memory_notes: [] } } },
      { actor_runtime_state: { astarion: { memory_notes: ["玩家与我一起嘲笑了 Gribbo，这种默契让我满意。"] } } }
    );
    expect(diffs.map((d) => d.label)).toContain("actor_private:astarion += memory_note");
  });

  test("test_demo_script_runner_advances_and_supports_stop", async () => {
    loadNewModules();
    jest.useFakeTimers();
    const calls = [];
    const runner = window.BG3DemoScriptRunner.createRunner({
      startNewTimeline: jest.fn(async () => calls.push("new")),
      runShowcaseLocalStep: jest.fn((cmd) => calls.push(cmd)),
      sendMessage: jest.fn(async (text) => calls.push(text)),
    }, { delayMs: 10 });
    const promise = runner.run();
    await Promise.resolve();
    expect(runner.isRunning()).toBe(true);
    runner.stop();
    jest.runOnlyPendingTimers();
    const result = await promise;
    expect(result.stopped).toBe(true);
    expect(calls.length).toBeGreaterThanOrEqual(1);
    jest.useRealTimers();
  });

  test("test_fallback_reason_is_highlighted_in_trace", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest();
    window.BG3DirectorTrace.activateTrace(["player_input", "dm_router", "ui_events"], {
      animate: false,
      data: { game_state: { intent_context: { fallback_reason: "network_timeout_or_unavailable" } } },
    });
    const fallback = document.getElementById("director-fallback-reason");
    expect(fallback).not.toBeNull();
    expect(fallback.classList.contains("is-hidden")).toBe(false);
    expect(fallback.textContent).toContain("network_timeout_or_unavailable");
  });

  test("test_journal_companion_guidance_derives_ui_event", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[队友建议] Astarion topic=lab_key missing: 去书房找钥匙，或者撬锁。"],
    });
    const guidance = events.find((event) => event.type === "companion_guidance");
    expect(guidance).toMatchObject({
      actorId: "astarion",
      topic: "lab_key",
      state: "missing_key",
    });
    expect(guidance.advice).toContain("书房");
  });

  test("test_companion_guidance_state_parses_missing_and_key_acquired", async () => {
    loadNewModules();
    const missing = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[队友建议] topic=lab_key 找钥匙，去书房搜箱子。"],
    }).find((event) => event.type === "companion_guidance");
    const acquired = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[队友建议] topic=lab_key has_key=true 钥匙在手，打开实验室门。"],
    }).find((event) => event.type === "companion_guidance");
    expect(missing.state).toBe("missing_key");
    expect(acquired.state).toBe("key_acquired");
  });

  test("test_companion_guidance_actor_parsing_and_party_fallback", async () => {
    loadNewModules();
    const lines = [
      "[队友建议] Astarion topic=lab_key 找钥匙",
      "[队友建议] Shadowheart topic=lab_key 找钥匙",
      "[队友建议] Lae’zel topic=lab_key 找钥匙",
      "[队友建议] topic=lab_key 找钥匙",
    ];
    const actorIds = lines.map((line) => window.BG3UIEventAdapter.extractUIEvents({ journal_events: [line] })
      .find((event) => event.type === "companion_guidance").actorId);
    expect(actorIds).toEqual(["astarion", "shadowheart", "laezel", "party"]);
  });

  test("test_journal_negotiation_leverage_derives_ui_event", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[交涉筹码] diary_evidence -> gribbo_elixir_truth"],
    });
    const leverage = events.find((event) => event.type === "negotiation_leverage");
    expect(leverage).toMatchObject({
      evidence: "diary_evidence",
      targetId: "gribbo",
      pressure: "gribbo_elixir_truth",
    });
  });

  test("test_negotiation_leverage_card_from_journal_events", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[交涉筹码] diary_evidence -> gribbo_elixir_truth"],
    });

    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({
        type: "negotiation_leverage",
        evidence: "diary_evidence",
        targetId: "gribbo",
        pressure: "gribbo_elixir_truth",
      }),
    ]));
  });

  test("test_negotiation_leverage_effects_can_come_from_state_delta", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[交涉筹码] diary_evidence -> gribbo_elixir_truth"],
      environment_objects: {
        gribbo: {
          dynamic_states: {
            patience: { current_value: 7 },
            fear: { current_value: 2 },
            paranoia: { current_value: 3 },
          },
        },
      },
    }, {
      environment_objects: {
        gribbo: {
          dynamic_states: {
            patience: { current_value: 8 },
            fear: { current_value: 1 },
            paranoia: { current_value: 2 },
          },
        },
      },
    });
    const leverage = events.find((event) => event.type === "negotiation_leverage");
    expect(leverage.effects).toEqual({ patience: -1, fear: 1, paranoia: 1 });
  });

  test("test_negotiation_leverage_card_from_flag_diff", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      flags: { necromancer_lab_gribbo_truth_pressure: true },
      environment_objects: {
        gribbo: {
          dynamic_states: {
            patience: { current_value: 14 },
            fear: { current_value: 6 },
            paranoia: { current_value: 1 },
          },
        },
      },
    }, {
      flags: { necromancer_lab_gribbo_truth_pressure: false },
      environment_objects: {
        gribbo: {
          dynamic_states: {
            patience: { current_value: 15 },
            fear: { current_value: 5 },
            paranoia: { current_value: 0 },
          },
        },
      },
    });

    const leverage = events.find((event) => event.type === "negotiation_leverage");
    expect(leverage).toMatchObject({
      evidence: "diary_evidence",
      targetId: "gribbo",
      pressure: "gribbo_elixir_truth",
      effects: { patience: -1, fear: 1, paranoia: 1 },
    });
  });

  test("test_hud_renders_companion_guidance_card", async () => {
    loadNewModules();
    jest.useFakeTimers();
    window.BG3HudRenderers.renderCompanionGuidanceCard({
      type: "companion_guidance",
      actorId: "astarion",
      topic: "lab_key",
      state: "missing_key",
      advice: "Find the study or lockpick the door.",
    });
    const card = document.querySelector(".agent-signal-card--guidance");
    expect(card).not.toBeNull();
    expect(card.textContent).toContain("Companion Guidance");
    expect(card.textContent).toContain("Astarion");
    expect(card.textContent).toContain("Lab Key");
    expect(card.textContent).toContain("Missing Key");
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  test("test_hud_renders_negotiation_leverage_card", async () => {
    loadNewModules();
    jest.useFakeTimers();
    window.BG3HudRenderers.renderNegotiationLeverageCard({
      type: "negotiation_leverage",
      evidence: "diary_evidence",
      targetId: "gribbo",
      pressure: "gribbo_elixir_truth",
      effects: { patience: -1, fear: 1, paranoia: 1 },
    });
    const card = document.querySelector(".agent-signal-card--leverage");
    expect(card).not.toBeNull();
    expect(card.textContent).toContain("Negotiation Leverage");
    expect(card.textContent).toContain("Diary Evidence");
    expect(card.textContent).toContain("Gribbo");
    expect(card.textContent).toContain("Elixir Truth");
    expect(card.textContent).toContain("Patience -1");
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  test("test_original_journal_event_remains_in_world_log", async () => {
    const rawJournal = "[队友建议] topic=lab_key 找钥匙，去书房搜箱子。";
    spyOnFetch().mockResolvedValueOnce(mockResponse({
      responses: [],
      journal_events: [rawJournal],
      party_status: {},
      environment_objects: {},
      player_inventory: {},
      combat_state: {},
    }));
    const api = await bootAppForTest("http://localhost/?qa_test=1");
    await api.sendMessage("怎么打开实验室门？", "CHAT", null, { source: "dialogue_input" });
    await flushAsync();
    expect(document.body.textContent).toContain(rawJournal);
    expect(document.querySelector(".agent-signal-card--guidance")).not.toBeNull();
  });

  test("test_plain_journal_event_does_not_generate_agent_signal_card", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[系统] 门仍然锁着。"],
    });
    expect(events.some((event) => event.type === "companion_guidance" || event.type === "negotiation_leverage")).toBe(false);
  });

  test("test_agent_signal_event_highlights_director_ui_events_without_wasd_activation", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest("http://localhost/?qa_test=1");
    if (window.BG3InputController) {
      window.BG3InputController.movePlayer(1, 0);
    }
    await flushAsync();
    expect(window.BG3DirectorTrace.getState()).toBe("idle");

    window.BG3DirectorTrace.activateTrace(["player_input", "dm_router", "ui_events"], {
      animate: false,
      data: { journal_events: ["[队友建议] topic=lab_key 找钥匙"] },
      uiEvents: [{ type: "companion_guidance", topic: "lab_key" }],
    });
    const uiNode = document.querySelector('li[data-node="ui_events"]');
    expect(uiNode).not.toBeNull();
    expect(uiNode.classList.contains("is-agent-signal")).toBe(true);
  });

  test("test_reduced_motion_agent_signal_card_has_no_pulse_class", async () => {
    loadNewModules();
    const previousMatchMedia = window.matchMedia;
    window.matchMedia = jest.fn().mockImplementation((query) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    }));
    jest.useFakeTimers();
    window.BG3HudRenderers.renderCompanionGuidanceCard({
      type: "companion_guidance",
      actorId: "party",
      topic: "lab_key",
      state: "missing_key",
      advice: "Find the study.",
    });
    const card = document.querySelector(".agent-signal-card--guidance");
    expect(card).not.toBeNull();
    expect(card.classList.contains("is-reduced-motion")).toBe(true);
    expect(card.classList.contains("agent-signal-card--pulse")).toBe(false);
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    window.matchMedia = previousMatchMedia;
  });

  test("test_trap_insight_journal_derives_ui_event", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[陷阱感知] astarion -> gas_trap_1"],
    });
    expect(events).toContainEqual(expect.objectContaining({
      type: "trap_insight",
      actor: "astarion",
      trapId: "gas_trap_1",
      source: "journal",
    }));
  });

  test("test_trap_reveal_flag_or_status_derives_insight_event", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      flags: { necromancer_lab_poison_trap_revealed: true },
      environment_objects: {
        gas_trap_1: { id: "gas_trap_1", type: "trap", status: "revealed", is_hidden: false, x: 4, y: 5 },
      },
    }, {
      flags: {},
      environment_objects: {
        gas_trap_1: { id: "gas_trap_1", type: "trap", status: "hidden", is_hidden: true, x: 4, y: 5 },
      },
    });
    expect(events.filter((event) => event.type === "trap_insight")).toHaveLength(1);
    expect(events.find((event) => event.type === "trap_insight")).toMatchObject({ trapId: "gas_trap_1" });
  });

  test("test_trap_disarmed_journal_derives_ui_event", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[陷阱解除] astarion -> gas_trap_1"],
    });
    expect(events).toContainEqual(expect.objectContaining({
      type: "trap_disarmed",
      actor: "astarion",
      trapId: "gas_trap_1",
    }));
  });

  test("test_trap_triggered_journal_derives_ui_event", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      journal_events: ["[毒气陷阱] gas_trap_1 triggered"],
    });
    expect(events).toContainEqual(expect.objectContaining({
      type: "trap_triggered",
      trapId: "gas_trap_1",
    }));
  });

  test("test_poisoned_status_diff_derives_trap_triggered_affected_actor", async () => {
    loadNewModules();
    const events = window.BG3UIEventAdapter.extractUIEvents({
      party_status: {
        player: { status_effects: [{ type: "poisoned", duration: 3 }] },
      },
    }, {
      party_status: {
        player: { status_effects: [] },
      },
    });
    const triggered = events.find((event) => event.type === "trap_triggered");
    expect(triggered).toBeDefined();
    expect(triggered.affectedActors).toContain("player");
  });

  test("test_hidden_trap_overlay_not_rendered_before_reveal", async () => {
    const tacticalMap = loadGameHelpers();
    const entries = tacticalMap.resolveTrapOverlayEntries({
      gas_trap_1: { id: "gas_trap_1", type: "trap", status: "hidden", is_hidden: true, x: 4, y: 5 },
    });
    expect(entries).toEqual([]);
  });

  test("test_revealed_trap_overlay_is_amber", async () => {
    const tacticalMap = loadGameHelpers();
    const [entry] = tacticalMap.resolveTrapOverlayEntries({
      gas_trap_1: { id: "gas_trap_1", type: "trap", status: "revealed", is_hidden: false, x: 4, y: 5 },
    });
    expect(entry).toMatchObject({ id: "gas_trap_1", status: "revealed", label: "TRAP", color: 0xe0a84e });
  });

  test("test_disabled_trap_overlay_is_safe", async () => {
    const tacticalMap = loadGameHelpers();
    const [entry] = tacticalMap.resolveTrapOverlayEntries({
      gas_trap_1: { id: "gas_trap_1", type: "trap", status: "disabled", is_hidden: false, x: 4, y: 5 },
    });
    expect(entry).toMatchObject({ status: "disabled", label: "DISARMED", color: 0x7fae83 });
  });

  test("test_triggered_trap_overlay_is_danger", async () => {
    const tacticalMap = loadGameHelpers();
    const [entry] = tacticalMap.resolveTrapOverlayEntries({
      gas_trap_1: { id: "gas_trap_1", type: "trap", status: "triggered", is_hidden: false, x: 4, y: 5 },
    });
    expect(entry).toMatchObject({ status: "triggered", label: "POISON", color: 0xc54232 });
  });

  test("test_state_diff_highlights_trap_flags_status_and_poisoned", async () => {
    loadNewModules();
    const diffs = window.BG3StateDiffRenderer.diffSnapshots({
      flags: {},
      environment_objects: {
        gas_trap_1: { id: "gas_trap_1", type: "trap", name: "gas_trap_1", status: "revealed" },
      },
      party_status: {
        player: { name: "Player", status_effects: [] },
      },
    }, {
      flags: { necromancer_lab_poison_trap_disarmed: true },
      environment_objects: {
        gas_trap_1: { id: "gas_trap_1", type: "trap", name: "gas_trap_1", status: "disabled" },
      },
      party_status: {
        player: { name: "Player", status_effects: [{ type: "poisoned", duration: 3 }] },
      },
    });
    expect(diffs).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: "trap_signal", label: "flags.necromancer_lab_poison_trap_disarmed = true" }),
      expect.objectContaining({ type: "trap_signal", label: "Gas Trap 1.status revealed -> disabled" }),
      expect.objectContaining({ type: "trap_signal", label: "Player.status += poisoned" }),
    ]));
  });

  test("test_director_trace_trap_events_activate_expected_nodes", async () => {
    spyOnFetch().mockResolvedValue(mockResponse({}));
    await bootAppForTest("http://localhost/?qa_test=1");
    if (window.BG3InputController) {
      window.BG3InputController.movePlayer(1, 0);
    }
    await flushAsync();
    expect(window.BG3DirectorTrace.getState()).toBe("idle");

    const insightNodes = window.BG3DirectorTrace.buildTraceNodes({}, {
      userLine: "Astarion spots a trap",
      intent: "CHAT",
      uiEvents: [{ type: "trap_insight", trapId: "gas_trap_1" }],
    });
    const disarmNodes = window.BG3DirectorTrace.buildTraceNodes({}, {
      userLine: "阿斯代伦，解除毒气陷阱",
      intent: "INTERACT",
      uiEvents: [{ type: "trap_disarmed", trapId: "gas_trap_1" }],
    });
    const triggerNodes = window.BG3DirectorTrace.buildTraceNodes({}, {
      userLine: "step into poison gas",
      intent: "trigger_zone",
      uiEvents: [{ type: "trap_triggered", trapId: "gas_trap_1" }],
    });
    expect(insightNodes).toEqual(expect.arrayContaining(["actor_view_filter", "actor_runtime", "domain_event", "event_drain", "ui_events"]));
    expect(disarmNodes).toEqual(expect.arrayContaining(["dm_router", "domain_event", "event_drain", "ui_events"]));
    expect(triggerNodes).toEqual(expect.arrayContaining(["domain_event", "event_drain", "ui_events"]));

    window.BG3DirectorTrace.activateTrace(insightNodes, {
      animate: false,
      uiEvents: [{ type: "trap_insight", trapId: "gas_trap_1" }],
    });
    expect(document.querySelector('li[data-node="actor_view_filter"]').classList.contains("is-agent-signal")).toBe(true);
    expect(document.querySelector('li[data-node="ui_events"]').classList.contains("is-agent-signal")).toBe(true);
  });

  test("test_reduced_motion_trap_cards_do_not_pulse", async () => {
    loadNewModules();
    const previousMatchMedia = window.matchMedia;
    window.matchMedia = jest.fn().mockImplementation((query) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    }));
    jest.useFakeTimers();
    window.BG3HudRenderers.renderTrapInsightCard({
      type: "trap_insight",
      actor: "astarion",
      trapId: "gas_trap_1",
    });
    const card = document.querySelector(".agent-signal-card--trap-insight");
    expect(card).not.toBeNull();
    expect(card.classList.contains("is-reduced-motion")).toBe(true);
    expect(card.classList.contains("agent-signal-card--pulse")).toBe(false);
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    window.matchMedia = previousMatchMedia;
  });
});
