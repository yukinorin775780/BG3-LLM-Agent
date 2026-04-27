# V1.3 Party Turn Coordinator (Thread B)

## Goal
- Keep the existing graph topology.
- Let one player input deterministically trigger multiple runtime-enabled companions in a single turn.
- Keep all state mutation inside `DomainEvent -> EventDrain`.

## Placement And Wiring
- New module: `core/actors/party_turn.py`
- Minimal integration point: `core/graph/nodes/actor_invocation.py`
- No change to `core/graph/graph_builder.py` edges/topology.

## Responsibility Boundaries
- `Party Turn Coordinator`:
  - Collect candidates from `current_speaker + speaker_queue` in stable order.
  - Filter obvious non-eligible actors (dead/hostile).
  - Invoke runtime actor-by-actor.
  - Aggregate `ActorDecision` metadata, `DomainEvent`, and reflection requests.
  - Return fallback actors that should continue through legacy generation.
- `ActorRuntime`:
  - Produces decision/events only.
  - Does not mutate world state directly.
- `EventDrain`:
  - Applies all pending domain events and performs state writeback.
- `Generation fallback`:
  - Still available for non-runtime actors.
  - Explicit telemetry marker: `mode=legacy`, `reason=party_turn_fallback_generation`.

## Deterministic Ordering Strategy
- Input candidate order is fixed:
  1. `current_speaker`
  2. `speaker_queue` (original order)
- Duplicate actor IDs are removed while preserving first appearance.
- Runtime invocation uses this exact order.
- Resulting `actor_spoke` events keep invocation order.
- Final response list order is produced by EventDrain from ordered events.

## Telemetry Markers
- Multi-runtime party turn marker:
  - `event_name=actor_runtime_decision`
  - payload includes `reason=party_turn_runtime_multi`
- Legacy fallback marker:
  - `event_name=actor_runtime_decision`
  - payload includes `mode=legacy`, `reason=party_turn_fallback_generation`

## Runtime Semantics Added For Narrative Loop Validation
- Added deterministic party-choice reaction branch in `TemplateActorRuntime`:
  - `civilian_priority_choice`
  - `mercy_choice`
- Each reacting actor emits:
  - `actor_spoke`
  - `actor_memory_update_requested` (actor-scoped note)
- Still no direct world-state mutation from runtime.

## Covered Cases
- `party_banter_after_player_choice`
- `laezel_disagrees_with_mercy_choice`

## Current Limitations
- Actor-level flag visibility remains prefix-based (`PUBLIC_FLAG_PREFIXES`).
- Coordinator currently uses lightweight eligibility + ordered orchestration only (no advanced tension scorer yet).
- Party-level same-turn arbitration policy is deterministic and simple; richer policy hooks are backlog.
