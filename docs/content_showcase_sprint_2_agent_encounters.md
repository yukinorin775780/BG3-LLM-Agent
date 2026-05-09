# Content Showcase Sprint 2: Player-Perceivable Agentic Characters

## 1. Strategy

The goal is no longer to add more backend agent infrastructure.
The goal is to make existing AI agent capabilities visible to the player through playable encounters.

Content Showcase Sprint 2 should turn the frozen Necromancer Lab V2 backend into short, replayable scenes where the player can point to a specific moment and say: "that companion knew something different", "that companion remembered what I did", or "the world state changed what the party advised."

## 2. Design Principles

- Player perception first: if the player cannot see the difference in dialogue, UI, or state, the encounter is not doing its job.
- One encounter should demonstrate one primary agent capability, with secondary systems only supporting the scene.
- Prefer short, replayable scenes over long lore; each encounter should fit into one or two player turns.
- Use existing backend contracts: ActorView, MemoryService, ActorRuntime, DomainEvent, EventDrain, GameService, skill checks, item transactions, flags.
- Every encounter needs observable frontend feedback: dialogue, toast, dice card, state diff, director trace, affection chip, memory card, inventory diff, or map highlight.
- Every encounter needs a golden/eval acceptance point that proves the player-visible behavior is backed by state.
- No new infra unless absolutely necessary; allowed changes are tiny runtime branches, flags, memory notes, dialogue triggers, frontend labels, and golden cases.

## 3. Encounter Overview Table

| ID | Encounter | Primary Capability | Player-Visible Moment | Required New Mechanic |
| --- | --- | --- | --- | --- |
| S2-A | The Trap Only Astarion Saw | ActorView + Perception + private knowledge | Asking each companion about the corridor gives three different answers from three different visible contexts. | Small ask-companion trigger branch; optional map highlight if Astarion warns. |
| S2-B | Astarion Remembers the Insult | actor_private memory + affection | Astarion either refuses to help because the player rebuked him earlier, or proactively helps if supported. | Runtime branch reading Astarion private memory and affection. |
| S2-C | The Diary Changes the Negotiation | State-driven behavior + memory retrieval | A decoded diary lets the player confront Gribbo with specific poison/key facts; failure only allows generic bargaining. | Gribbo dialogue branch keyed by diary flags and party/shared memory. |
| S2-D | The Party Splits on Mercy | Party Turn Coordinator + values conflict | Shadowheart, Lae'zel, and Astarion argue in the same turn over Gribbo's fate; player choice shifts affection. | New mercy-choice branch plus affection/memory DomainEvents. |
| S2-E | The Key Is Not Just an Item | DomainEvent/EventDrain + state consistency | Looting the lab key visibly changes inventory, flags, and companion advice about the exit. | Post-key advice branch keyed by inventory/flag; frontend inventory/state diff copy. |

## 4. Encounter Details

## Encounter 1: The Trap Only Astarion Saw

### Purpose

Show that ActorView and private perception matter: Astarion knows the corridor contains a mechanical poison threat, Shadowheart only senses necromantic residue, and Lae'zel sees the delay as tactical weakness.

### Player Setup

- Player is in the safe room or poison corridor approach.
- `necromancer_lab_intro_seen=true`.
- Act 1 perception setup already ran.
- `astarion_detected_gas_trap` exists with actor-scoped visibility for Astarion.
- `shadowheart_senses_necromancy` exists with actor-scoped visibility for Shadowheart.
- `gas_trap_1.is_hidden=true`.

### Trigger

Player asks the party for advice before entering the corridor, for example:

- "Ask Astarion what he sees ahead."
- "Ask Shadowheart if she senses anything."
- "Ask Lae'zel what we should do."
- "Ask everyone how to cross the corridor."

### Scene Beat

1. The player stops before the poison corridor and asks for advice.
2. Astarion warns about a pressure seam, chemical bite in the air, or trap trigger without exposing raw trap metadata.
3. Shadowheart disagrees on certainty: she senses necromantic contamination, not the exact mechanism.
4. Lae'zel pushes for speed, suggesting a direct rush or forced advance.
5. The UI shows that these are companion perspectives, not omniscient narrator output.
6. If the player follows Astarion's advice, the corridor gets a subtle map highlight or "trap suspected" toast.
7. If the player ignores him, the existing trap route remains available.

### Agent Capability Exposed

- ActorView? Yes. Each companion response is based on visible flags and objects filtered to that actor.
- Memory? No primary memory requirement.
- Party Coordinator? Optional, if asking everyone in one turn.
- DomainEvent? Optional `actor_spoke`; no required state mutation beyond existing flags.
- State-driven behavior? Yes, because advice depends on detected/scoped flags.

### Required State

- flags:
  - `necromancer_lab_intro_seen=true`
  - `world_necromancer_lab_trap_warned=true`
  - `astarion_detected_gas_trap` actor-scoped to `astarion`
  - `shadowheart_senses_necromancy` actor-scoped to `shadowheart`
  - optional new `necromancer_lab_corridor_party_advice_seen=true`
- memory notes:
  - optional Astarion actor-private note: "noticed poison trap signs near corridor"
- inventory:
  - none
- affection:
  - no change required
- actor state:
  - Shadowheart may retain `tense`
  - party members alive and eligible

### Expected Frontend Signals

- dialogue: three distinct companion advice lines.
- toast: "Astarion suspects a trap" if his warning is selected.
- dice card: optional if tied to a visible perception check recap.
- state diff: optional new `necromancer_lab_corridor_party_advice_seen`.
- director trace: `ActorView` or `party_turn_runtime_multi` marker.
- map highlight: suspected corridor tile or trap zone, without revealing exact hidden trap id.
- affection chip: none.
- memory card: optional Astarion private note if debug view is enabled.

### Backend Touchpoints

- ActorRuntime reads each companion's ActorView.
- ActorView filters scoped flags and hidden environment objects.
- Party Turn Coordinator can be used for "ask everyone" input.
- EventDrain applies optional `actor_spoke` and optional memory note events.
- GameService keeps response shape unchanged.
- Existing Act 1 intro/perception node provides the required flags.
- New tiny branch if needed: route "ask companion about corridor/trap" to deterministic companion advice.

### Golden / Eval Acceptance

- response contains:
  - Astarion mentions a trap/poison/mechanism.
  - Shadowheart mentions necromancy/deathly residue but not exact trap metadata.
  - Lae'zel recommends direct action or speed.
- state equals:
  - `gas_trap_1.is_hidden=true` remains hidden.
  - optional `necromancer_lab_corridor_party_advice_seen=true`.
- telemetry contains:
  - actor invocation for requested companions.
  - ActorView filtering marker if available.
- memory note exists:
  - optional Astarion private perception note only under Astarion/player debug visibility.
- event_drain applied:
  - pending events drained if `actor_spoke` or memory events are emitted.

### Implementation Cost

S. Recommended first implementation.

### Risk

The biggest risk is accidentally making the narrator or all companions reveal the exact hidden trap. The scene must preserve hidden trap metadata while still giving the player useful, differentiated advice.

## Encounter 2: Astarion Remembers the Insult

### Purpose

Show actor-private memory and affection changing later behavior. Astarion should not just react once in Act 3; he should remember whether the player supported or humiliated him when later asked for practical help.

### Player Setup

- Player previously completed Act 3 Gribbo negotiation branch.
- Branch A: player sided with Astarion, producing positive affection and private memory.
- Branch B: player rebuked Astarion, producing negative affection and private memory.
- Player later asks Astarion to help with a lock, hidden door, or lab search.

### Trigger

Player asks Astarion for help after the negotiation, for example:

- "Astarion, check that lock."
- "Can you find the hidden door?"
- "You are good with locks. Help me open this."

### Scene Beat

1. The player reaches a locked or suspicious lab object after the Gribbo argument.
2. The player asks Astarion to help.
3. If the player rebuked him, Astarion references the earlier insult and either refuses, delays, or gives a colder minimal hint.
4. If the player supported him, Astarion proactively points out the lock seam, keyhole, or shortcut.
5. The UI shows an affection chip or memory card explaining that this is a remembered relationship consequence.
6. The player can still progress through key use, lockpick, or alternate route; the encounter changes help quality, not critical path availability.

### Agent Capability Exposed

- ActorView? Yes, Astarion can see his own private memory and relevant object.
- Memory? Yes, actor_private memory is the primary capability.
- Party Coordinator? No.
- DomainEvent? Yes, prior Act 3 memory/affection events must have landed; optional new memory note for this response.
- State-driven behavior? Yes, branch depends on affection and private memory.

### Required State

- flags:
  - `necromancer_lab_gribbo_combat_triggered=true`
  - `necromancer_lab_player_sided_with_astarion=true/false`
  - optional new `necromancer_lab_astarion_help_requested=true`
- memory notes:
  - positive: Astarion remembers the player backed his mockery of Gribbo.
  - negative: Astarion remembers the player told him to shut up during negotiation.
- inventory:
  - optional `lockpick` or missing `heavy_iron_key`, depending on target object.
- affection:
  - positive branch expects Astarion affection increased by prior event.
  - negative branch expects Astarion affection decreased by prior event.
- actor state:
  - Astarion alive, in party, non-hostile.

### Expected Frontend Signals

- dialogue: Astarion quotes or paraphrases the earlier player treatment.
- toast: "Astarion remembers how you treated him."
- dice card: optional lockpick/perception card if help grants advantage or a hint.
- state diff: optional `necromancer_lab_astarion_help_requested=true`.
- director trace: ActorRuntime branch reads actor_private memory.
- map highlight: optional lock/hidden-door highlight in positive branch.
- affection chip: show prior or current Astarion affection context.
- memory card: Astarion private memory note.

### Backend Touchpoints

- ActorRuntime for Astarion checks actor_private memory notes and affection.
- MemoryService supplies Astarion's private relationship note.
- ActorView ensures other companions do not receive the private memory as their own context.
- EventDrain has already applied Act 3 affection/memory events.
- Existing hidden door, lock, or item gating node can be reused.
- New tiny branch if needed: Astarion lock/search help response keyed by prior memory.

### Golden / Eval Acceptance

- response contains:
  - negative branch: Astarion references the rebuke/insult and withholds full help.
  - positive branch: Astarion references support or acts more helpfully.
- state equals:
  - no critical path softlock; door/key/alternate solution remains available.
  - affection values reflect prior Act 3 branch.
- telemetry contains:
  - ActorRuntime invocation for Astarion.
  - memory lookup or runtime branch marker for relationship memory.
- memory note exists:
  - Astarion actor_private Act 3 memory remains present.
  - optional new note records that he was asked for help afterward.
- event_drain applied:
  - no pending events left after optional memory update.

### Implementation Cost

S to M. Recommended first implementation if the prior Act 3 branch is already stable in the target demo path.

### Risk

The biggest risk is making Astarion's refusal block progression. The refusal must affect flavor, hint quality, advantage, or route clarity, not make the demo unwinnable.

## Encounter 3: The Diary Changes the Negotiation

### Purpose

Show state-driven behavior and memory retrieval: reading and decoding the necromancer diary should materially change what the player can say to Gribbo and how Gribbo reacts.

### Player Setup

- Player has reached Gribbo negotiation.
- Success path: `necromancer_lab_diary_decoded=true` and party/shared diary memory exists.
- Failure path: `necromancer_lab_diary_decoded=false`, only fragmented private memory exists.
- Control path: diary not read.

### Trigger

Player confronts Gribbo with diary knowledge or asks about the potion/key connection, for example:

- "The diary says your potion is tied to the gas. Tell us the truth."
- "I know about the heavy iron key and the unfinished antidote."
- "What did the necromancer do to you?"

### Scene Beat

1. The player opens negotiation with Gribbo.
2. If the diary was decoded, the player gets a specific confrontation line about poison, antidote, Gribbo, and the key.
3. Gribbo reacts defensively because the player knows facts he expected to be secret.
4. Shadowheart can add a short warning that the diary knowledge is dangerous but useful.
5. If the diary was not decoded, the same player intent falls back to vague pressure or generic bargaining.
6. The UI shows a memory or state chip linking the stronger line to decoded diary knowledge.
7. Negotiation still resolves through existing Gribbo branches; this encounter adds a visible state-dependent opening.

### Agent Capability Exposed

- ActorView? Yes, runtime should only use diary facts if visible through player/party state.
- Memory? Yes, party_shared or player private diary memory is retrieved.
- Party Coordinator? Optional Shadowheart follow-up.
- DomainEvent? Optional actor_spoke; existing diary memory events are prerequisite.
- State-driven behavior? Yes, decoded/failed/unread diary state changes the dialogue branch.

### Required State

- flags:
  - `necromancer_lab_diary_read=true/false`
  - `necromancer_lab_diary_decoded=true/false`
  - `necromancer_lab_key_hint_known` party-scoped on success
  - `necromancer_lab_antidote_formula_fragment_known` actor-scoped on success
  - optional new `necromancer_lab_gribbo_confronted_with_diary=true`
- memory notes:
  - success: player actor_private and `__party_shared__` notes mention Gribbo, gas, key, and unfinished antidote.
  - failure: player actor_private note only contains fragments.
- inventory:
  - none required.
- affection:
  - no direct change required.
- actor state:
  - Gribbo alive, neutral/dialogue target.

### Expected Frontend Signals

- dialogue: successful path includes specific diary-based accusation; failure path is visibly less informed.
- toast: "Diary knowledge unlocked a new negotiation angle."
- dice card: optional persuasion/intimidation card after the specific reveal.
- state diff: optional `necromancer_lab_gribbo_confronted_with_diary=true`.
- director trace: branch reason includes diary decoded state.
- map highlight: none.
- affection chip: optional Shadowheart approval if player uses forbidden knowledge responsibly.
- memory card: party_shared diary summary or player private diary note.

### Backend Touchpoints

- GameService routes Gribbo dialogue as existing Act 3 negotiation.
- ActorRuntime/DM branch checks diary flags and memory availability.
- MemoryService retrieves party_shared diary note.
- ActorView prevents using antidote details if only a non-speaking actor privately knows them.
- EventDrain applies optional flag/memory events.
- Existing Gribbo node remains the negotiation anchor.
- New tiny branch if needed: `gribbo_diary_confrontation_success/failure/unread`.

### Golden / Eval Acceptance

- response contains:
  - decoded path: poison/gas, key, Gribbo, and unfinished antidote or potion truth.
  - failed/unread path: no precise antidote/key accusation.
- state equals:
  - decoded flags unchanged and available.
  - optional `necromancer_lab_gribbo_confronted_with_diary=true`.
- telemetry contains:
  - branch marker keyed to `necromancer_lab_diary_decoded`.
- memory note exists:
  - success path has party_shared diary summary.
  - failure path lacks party_shared complete diary summary.
- event_drain applied:
  - optional confrontation flag drained; no pending events.

### Implementation Cost

S. Recommended first implementation.

### Risk

The biggest risk is leaking success-only diary facts on failed or unread paths. The golden must assert absence of precise facts, not just presence on the success path.

## Encounter 4: The Party Splits on Mercy

### Purpose

Show Party Turn Coordinator and value conflict. One player choice about Gribbo should cause multiple companions to answer in the same turn from distinct values, then write visible affection and memory consequences.

### Player Setup

- Gribbo is defeated, cornered, or otherwise at the player's mercy.
- Combat is over or paused in a deterministic post-conflict state.
- Party includes Astarion, Shadowheart, and Lae'zel.
- Player can choose one of three outcomes: execute, spare, or exploit Gribbo.

### Trigger

Player decides Gribbo's fate, for example:

- "Spare Gribbo. He is pathetic, not worth killing."
- "Execute Gribbo before he poisons anyone else."
- "Keep him alive until he gives us everything useful."

### Scene Beat

1. Gribbo is cornered and no longer controls the room.
2. The player proposes mercy, execution, or exploitation.
3. Shadowheart argues for measured mercy or consequence-aware restraint.
4. Lae'zel pushes for decisive elimination or domination.
5. Astarion favors leverage and mocks sentimental mercy.
6. The player confirms a choice.
7. The UI shows affection chips and memory/state diffs for the chosen stance.
8. The selected outcome writes a clear world flag so later banter can reference it.

### Agent Capability Exposed

- ActorView? Yes, each companion sees public outcome state plus their private values.
- Memory? Yes, each companion writes actor_private reaction memory.
- Party Coordinator? Yes, this is the primary capability.
- DomainEvent? Yes, affection, memory, and world flag changes should flow through DomainEvent/EventDrain.
- State-driven behavior? Yes, choice changes future advice and reaction memory.

### Required State

- flags:
  - `world_necromancer_lab_gribbo_defeated=true` or equivalent cornered state.
  - new `necromancer_lab_gribbo_mercy_choice=spare|execute|exploit`
  - optional `necromancer_lab_party_mercy_debate_seen=true`
- memory notes:
  - Astarion actor_private reaction to player mercy/exploitation.
  - Shadowheart actor_private reaction to player mercy/execution.
  - Lae'zel actor_private reaction to player hesitation/decisiveness.
- inventory:
  - optional `heavy_iron_key`, depending on timing.
- affection:
  - suggested:
    - spare: Shadowheart +1, Lae'zel -1, Astarion -1
    - execute: Lae'zel +1, Shadowheart -1, Astarion 0
    - exploit: Astarion +1, Shadowheart -1, Lae'zel 0 or +1
- actor state:
  - Gribbo defeated/cornered and not already removed.
  - party members alive and eligible.

### Expected Frontend Signals

- dialogue: three companion reactions in the same turn.
- toast: "The party disagrees over Gribbo's fate."
- dice card: none required.
- state diff: `necromancer_lab_gribbo_mercy_choice`.
- director trace: `party_turn_runtime_multi`.
- map highlight: optional Gribbo entity highlight.
- affection chip: visible companion affection deltas.
- memory card: per-companion private memory update.

### Backend Touchpoints

- Party Turn Coordinator invokes Astarion, Shadowheart, and Lae'zel in stable order.
- ActorRuntime emits `actor_spoke`, affection change events, and memory update requests.
- EventDrain writes affection, memory, and mercy-choice flag.
- GameService response includes ordered actor lines and state diff.
- Existing Act 4 post-combat state can anchor the scene.
- New tiny branch if needed: deterministic `gribbo_mercy_choice` runtime branch.

### Golden / Eval Acceptance

- response contains:
  - Shadowheart argues from restraint/consequence.
  - Lae'zel argues from decisive strength.
  - Astarion argues from leverage or self-interest.
- state equals:
  - `necromancer_lab_gribbo_mercy_choice` matches player choice.
  - expected affection deltas applied.
- telemetry contains:
  - `actor_invocation_reason=party_turn_runtime_multi`.
  - ordered actor runtime decisions.
- memory note exists:
  - each companion has an actor_private note about the player's choice.
  - notes are not copied into other companions' private memory.
- event_drain applied:
  - pending events empty after affection/memory/flag writeback.

### Implementation Cost

M. Recommended Phase B after one lower-cost showcase branch is stable.

### Risk

The biggest risk is over-expanding into a new combat or prisoner system. Keep this as a post-combat narrative choice with flags, affection, and memory only.

## Encounter 5: The Key Is Not Just an Item

### Purpose

Show that DomainEvent/EventDrain and state consistency are player-visible. The lab key should not merely appear in inventory; it should change companion advice and the exit plan.

### Player Setup

- Gribbo has been defeated or convinced.
- `heavy_iron_key` is still on Gribbo or otherwise obtainable.
- `heavy_oak_door_1.is_open=false`.
- Player may ask the party what to do before or after looting the key.

### Trigger

Two-step trigger:

1. Player loots or receives `heavy_iron_key`.
2. Player asks "What now?", "How do we leave?", or approaches the heavy oak door.

### Scene Beat

1. Before obtaining the key, companions advise alternate routes: hidden door, lockpicking, or forcing the door.
2. Player loots or receives `heavy_iron_key`.
3. The UI shows an inventory diff and DomainEvent/EventDrain state diff.
4. When the player asks again, the party advice changes.
5. Astarion may say the lock is no longer the problem.
6. Lae'zel pushes to use the key and leave immediately.
7. Shadowheart warns that opening the door may still expose lingering poison or necromancy.
8. The heavy oak door interaction succeeds only because state now has the key.

### Agent Capability Exposed

- ActorView? Yes, companions see player inventory/world flags through allowed state.
- Memory? Optional, if companions remember the key was obtained.
- Party Coordinator? Optional, for group "what now?" advice.
- DomainEvent? Yes, this is the primary capability.
- State-driven behavior? Yes, advice changes based on key inventory/flag.

### Required State

- flags:
  - before: `necromancer_lab_gribbo_key_looted` absent or false.
  - after: `necromancer_lab_gribbo_key_looted=true` or `world_necromancer_lab_heavy_key_obtained=true`.
  - optional new `necromancer_lab_key_advice_seen=true`.
- memory notes:
  - optional party_shared note: "The party obtained the heavy iron key."
- inventory:
  - before: `player_inventory.heavy_iron_key` absent or 0.
  - after: `player_inventory.heavy_iron_key == 1`.
- affection:
  - no change required.
- actor state:
  - Gribbo no longer blocks looting or has transferred the key.
  - `heavy_oak_door_1.is_open=false` before interaction.

### Expected Frontend Signals

- dialogue: advice changes before vs after key acquisition.
- toast: "Heavy iron key obtained."
- dice card: none required.
- state diff: inventory delta and key flag.
- director trace: `actor_item_transaction_requested -> event_drain`.
- map highlight: heavy oak door highlighted after key acquisition.
- affection chip: none.
- memory card: optional party_shared key note.

### Backend Touchpoints

- Existing item transaction path for `heavy_iron_key`.
- DomainEvent emits `actor_item_transaction_requested`.
- EventDrain applies `gribbo -> player` transfer and key flag.
- GameService exposes updated state snapshot.
- ActorRuntime or deterministic advice branch reads inventory/flag.
- Existing heavy oak door interaction consumes or checks key as already implemented.
- New tiny branch if needed: post-key "what now" advice.

### Golden / Eval Acceptance

- response contains:
  - before key: advice mentions lockpick/hidden route/forcing or finding key.
  - after key: advice mentions using the key on the heavy oak door.
- state equals:
  - `player_inventory.heavy_iron_key == 1`.
  - `necromancer_lab_gribbo_key_looted=true` or equivalent key obtained flag.
  - `heavy_oak_door_1.is_open=true` after interaction.
- telemetry contains:
  - `actor_item_transaction_requested`.
  - `event_drain` transaction count.
- memory note exists:
  - optional party_shared key acquisition note.
- event_drain applied:
  - Gribbo loses the key.
  - player gains exactly one key.
  - duplicate loot does not duplicate key.

### Implementation Cost

S. Recommended first implementation because the transaction path already exists and the visible payoff is strong.

### Risk

The biggest risk is making the UI show the key diff while companion advice still follows the old no-key branch. The acceptance case must verify both state writeback and changed advice in the same replay.

## 5. Recommended Implementation Order

Phase A: implement 1-2 lowest-cost/highest-showcase encounters.

1. Implement Encounter 5: The Key Is Not Just an Item.
   - Highest reuse of existing Act 4 item transaction.
   - Strong player-visible state diff.
   - Low risk if scoped to post-key advice.
2. Implement Encounter 3: The Diary Changes the Negotiation.
   - Highest narrative payoff from existing Act 2 diary flags/memory.
   - Clear success/failure contrast for golden acceptance.
   - No new map or combat behavior.

Phase B: add golden cases.

- `necromancer_lab_s2_key_changes_party_advice`
- `necromancer_lab_s2_diary_changes_gribbo_negotiation`
- `necromancer_lab_s2_astarion_remembers_rebuke`
- `necromancer_lab_s2_actorview_trap_advice`
- `necromancer_lab_s2_party_mercy_split`

Phase C: add frontend signals.

- Add stable labels for inventory diff, affection chip, memory card, director trace, and map highlight where already supported.
- Prioritize signals that prove state changed: inventory diff for key, memory card for Astarion, affection chip for mercy split.

Phase D: optional polish.

- Add alternate wording variants for replay.
- Add one optional map highlight for Astarion's suspected trap and the heavy oak door.
- Add small companion follow-up banter after the player uses the key or resolves Gribbo's fate.

## 6. Backend Infra Decision

- New architecture required: no.
- New backend infra required: no.
- Only small runtime branch / flag / golden required: yes.
- Allowed implementation surface:
  - new flags
  - new memory notes
  - small deterministic ActorRuntime branches
  - small dialogue triggers
  - new golden cases
  - frontend copy/signals for state, memory, and event feedback

## 7. Main Risks

- Visibility leakage: success-only diary facts or hidden trap metadata may appear in generic narration or the wrong companion response.
- Softlock risk: Astarion's remembered insult must reduce help quality, not block required progression.
- Signal mismatch: frontend may show dialogue but not the state diff/memory/affection event that proves the agent capability.
- Branch overgrowth: the mercy scene can accidentally become a new prisoner/combat system; keep it as flags, affection, and memory.
- Golden weakness: acceptance must assert absence on failure paths, not only presence on success paths.
