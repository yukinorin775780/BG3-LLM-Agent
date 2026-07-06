# Demo Release 2026-07-06

## Result

PASS. Demo V5 is the current portfolio cut for the Web client.

## Public Cut

- Release tag: `demo-v5-20260706`
- Video: `final_demo_subtitled.mp4`
- Duration: 132.76 seconds
- Resolution: 1920x1080
- Format: H.264 MP4 with burnt-in English subtitles

## Recording Method

- Backend: `python server.py`
- Browser: Playwright Chromium
- URL shape: `/web_ui/?session_id=demo_v5_...&map_id=necromancer_lab&qa_no_idle=1`
- Allowed QA flag: `qa_no_idle=1`
- Forbidden during recording: `qa_showcase`, `qa_map_debug`, `/flag`, state injection, script-side direct `/api/chat` story progression
- Evidence: read-only `/api/state` snapshots plus Web UI screenshots

## Required Beats Covered

- Act 1 local WASD movement without narrative backend calls
- Act 2 Astarion Perception roll, safe interrupt, hidden trap reveal, and trap disarm
- B-D locked door, high-DC lockpick failure, and cracked-wall fail-forward route
- Act 3 Secret Study spatial entry, readable props, diary memory leverage, and lab key
- Return to B-D door before Act 4, avoiding Act3-to-Act4 teleport
- Act 4 Boss Lab readability, three-companion strategy split, and truth negotiation
- Backend tool trace during Act4 truth route:
  - `query_party_memory`
  - `check_target_inventory`
  - `roll_skill_check`
  - `transfer_item`
- Final exit opened with `heavy_iron_key`, ending in `demo_cleared=true`

## Final State Evidence

```json
{
  "demo_cleared": true,
  "act4_final_exit_opened": true,
  "heavy_iron_key": 1,
  "lab_key": 1,
  "visible_rooms": [
    "room_a_spawn",
    "room_b_corridor",
    "room_c_secret_study",
    "room_d_lab",
    "room_exit"
  ]
}
```

## Notes

V5 replaces V4 as the main README demo. V4 was useful as a guided showcase, but V5 is the stronger portfolio artifact because it records a fresh Web UI path and includes the real backend tool trace added after V4.
