const fs = require("fs");
const path = require("path");

const INDEX_HTML_PATH = path.resolve(__dirname, "../index.html");
const APP_JS_PATH = path.resolve(__dirname, "../app.js");

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

async function bootAppForTest() {
  window.history.replaceState({}, "", "http://localhost/?qa_test=1");
  window.__BG3_ENABLE_TEST_API__ = true;
  window.BG3TacticalMap = {
    update: jest.fn(),
    resize: jest.fn(),
  };
  if (typeof window.requestAnimationFrame !== "function") {
    window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  }

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
    mountIndexBody();
  });

  afterEach(() => {
    delete window.__BG3_APP_TEST_API__;
    delete window.__BG3_ENABLE_TEST_API__;
    delete window.BG3TacticalMap;
  });

  test("test_xray_panel_updates", async () => {
    const fetchSpy = spyOnFetch().mockResolvedValueOnce(
      mockResponse({
        last_node: "DM_NODE",
        entities: {
          gribbo: {
            dynamic_states: {
              patience: {
                current_value: 8,
                max_value: 20,
              },
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

    const dmNode = document.querySelector('#node-timeline li[data-node="dm_analysis"]');
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
      party_status: {
        gribbo: { name: "gribbo" },
      },
      environment_objects: {},
      combat_state: {},
      journal_events: ['[gribbo]: "离我远点。"'],
      responses: [],
    };
    const secondState = {
      active_dialogue_target: null,
      party_status: {
        gribbo: { name: "gribbo" },
      },
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
    expect(chatCall[0]).toBe("/api/chat");
    expect(chatCall[1].method).toBe("POST");

    const payload = JSON.parse(chatCall[1].body);
    expect(payload.user_input).toBe("我直接拔出武器攻击！");
  });
});
