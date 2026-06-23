# Demo Release 2026-06-22

This document records the current accepted portfolio demo cut for the Necromancer
Lab V2 Web vertical slice.

## Result

PASS.

The recording is suitable for README, GitHub, and portfolio use after uploading
the MP4 to a public host such as GitHub Releases.

Public release:

```text
https://github.com/yukinorin775780/BG3-LLM-Agent/releases/tag/demo-v2-20260622
```

Public MP4:

```text
https://github.com/yukinorin775780/BG3-LLM-Agent/releases/download/demo-v2-20260622/final_demo.mp4
```

## Video Assets

Local final cut:

```text
artifacts/demo_recording/full_web_demo_20260622T220713/final_demo.mp4
```

Local raw recording:

```text
artifacts/demo_recording/full_web_demo_20260622T220713/raw_recording.mp4
```

Supporting files:

```text
artifacts/demo_recording/full_web_demo_20260622T220713/shotlist.md
artifacts/demo_recording/full_web_demo_20260622T220713/narration_script_en.md
artifacts/demo_recording/full_web_demo_20260622T220713/narration_script_zh.md
artifacts/demo_recording/full_web_demo_20260622T220713/subtitles.srt
artifacts/demo_recording/full_web_demo_20260622T220713/acceptance_report.md
```

The `artifacts/` directory is intentionally ignored by Git, so the video is not
stored in the repository. The public copy is hosted as a GitHub Release asset.

## Recording Method

- Local backend: `python server.py`
- Browser: Playwright Chromium
- Resolution: 1920x1080
- Session: `necromancer_lab_v2_20260622T220713`
- URL:

```text
http://127.0.0.1:8000/web_ui/?session_id=necromancer_lab_v2_20260622T220713&map_id=necromancer_lab&qa_no_idle=1
```

Story progression used real Web UI actions only:

- WASD movement
- `E` interactions
- page input box
- page send button

Read-only `/api/state` calls were used for evidence snapshots.

Forbidden methods were not used:

- no `qa_showcase`
- no `qa_map_debug`
- no `/flag`
- no state injection
- no script-side direct `/api/chat` progression

## Demo Beats

1. **Act 1: Safe Room**
   Local WASD movement and party following happen without narrative backend calls.

2. **Act 2: Poison Corridor**
   Astarion rolls perception, identifies the trap, and can be ordered to disarm it.
   The successful perception interrupts unsafe movement and avoids poison gas.

3. **Act 2 Failure Route**
   The B-D lab door is locked. A failed lockpick reveals a cracked wall near the
   door instead of teleporting the player to the next act.

4. **Act 3: Secret Study**
   The player enters a connected side room, reads Chemical Notes, Iron Key Sketch,
   and Necromancer Diary, then loots `lab_key` from the Study Chest.

5. **Act 4: Gribbo Lab**
   The player returns to the lab door, opens it with `lab_key`, and encounters
   Gribbo. The party proposes conflicting strategies.

6. **Boss Resolution**
   Diary truth functions as encounter leverage. The heavy iron key is transferred
   through the runtime state path.

7. **Final Exit**
   The player opens the final exit with `heavy_iron_key`; `demo_cleared=true`.

## Acceptance Evidence

Final assertions from the accepted run:

```text
demo_cleared=true
act4_final_exit_opened=true
player_inventory.heavy_iron_key=1
player_inventory.lab_key=1
```

Observed request/runtime checks:

- no `/api/chat` 500
- no traceback
- no fixture fallback warning
- no browser runtime error
- local WASD movement did not call `/api/chat`

Scene expression score from the acceptance report: `9.3 / 10`.

## Publishing Checklist

1. Keep the GitHub Release asset available:
   `https://github.com/yukinorin775780/BG3-LLM-Agent/releases/tag/demo-v2-20260622`
2. Optionally add a thumbnail or animated GIF derived from the first 20-30 seconds.
3. Keep `raw_recording.mp4`, `subtitles.srt`, and narration scripts locally for
   future voiceover or subtitle edits.
4. If voiceover is added, generate a new public cut but keep this document as the
   baseline accepted silent-subtitle version.
