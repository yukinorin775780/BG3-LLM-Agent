# Portfolio Demo Script

This is a short recording plan for presenting BG3 LLM Agent as a job portfolio
piece. The goal is to show player-perceivable AI behavior, not every backend detail.

## Target Length

60-90 seconds.

## Recording Setup

- Use a fresh session id.
- Use the playable map: `map_id=necromancer_lab`.
- Keep debug-only panels off unless recording a technical overlay segment.
- Show the Director Timeline only when it helps explain the agent pipeline.

Recommended URL:

```text
http://127.0.0.1:8000/web_ui/?session_id=portfolio_demo_001&map_id=necromancer_lab&qa_no_idle=1
```

## Shot List

### 1. Safe Room Intro

Show:

- party members visible
- local movement
- no LLM call for WASD movement

Talk track:

```text
This is a playable RPG vertical slice. Movement stays local and cheap.
Narrative interactions go through the agentic backend.
```

### 2. Astarion Detects the Trap

Trigger:

```text
Is something wrong in the corridor?
```

Show:

- Astarion bark/typewriter
- suspicious trap marker
- Director Timeline summary
- state diff for trap reveal

Talk track:

```text
Astarion detects a hidden trap through an actor-specific perception branch.
The trap is not globally leaked to every actor.
```

### 3. Astarion Disarms the Trap

Trigger:

```text
Astarion, disarm the trap.
```

Show:

- disarm feedback
- trap becomes safe
- no poison trigger

Talk track:

```text
The companion can execute a structured action. The result lands in game state,
not just in dialogue text.
```

### 4. Secret Study and Diary

Trigger:

```text
Read the chemical notes.
Read the necromancer diary.
```

Show:

- room C reveal
- diary context gathered
- memory/state diff

Talk track:

```text
The failed direct route becomes information. Reading the study changes what
the party knows before the final encounter.
```

### 5. Gribbo Boss Strategy

Trigger:

```text
How should we handle him?
```

Show:

- Astarion, Shadowheart, and Lae'zel strategy barks
- conflicting companion plans
- Director Timeline

Talk track:

```text
The party does not speak as one generic assistant. Each companion proposes a
different plan based on agenda and role.
```

### 6. Truth Negotiation and Escape

Trigger:

```text
I know what the potion did to you. You are not a guard. You are an experiment.
Give me the key and we will get you out.
```

Then open the final exit.

Show:

- heavy iron key transfer
- final exit opens
- demo cleared

Talk track:

```text
Earlier knowledge unlocks a social solution. The key transfer and final door
resolution are committed through deterministic event handling.
```

## What To Avoid In The Recording

- Do not dwell on setup screens.
- Do not show long raw JSON panels unless the audience is technical.
- Do not frame this as a complete CRPG.
- Do not over-explain LangGraph before showing player-facing behavior.

## Closing Line

```text
This is a vertical slice for player-perceivable AI characters: they perceive,
remember, disagree, act, and change the game state.
```
