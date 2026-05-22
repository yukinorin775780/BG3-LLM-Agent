# Dialogue Examples

These examples are intended for portfolio review. They show how player-facing
dialogue is connected to state, memory, and deterministic game consequences.

## 1. Actor-Specific Perception

```text
Player: Is something wrong in the corridor?

Astarion: Wait. Hidden gas trap.

State:
- act2_astarion_perception_checked=true
- act2_astarion_perception_success=true
- act2_gas_trap_revealed=true
```

What this demonstrates:

- Astarion can notice something before the player sees full trap metadata.
- The reveal is written as game state and reflected in the UI.
- This is not a generic narrator hint.

## 2. Companion Executes A Command

```text
Player: Astarion, disarm the trap.

Astarion: Done. The mechanism will not bite again.

State:
- act2_gas_trap_disarmed=true
- gas_trap_1.status=disabled
- journal: [陷阱解除] astarion -> gas_trap_1
```

What this demonstrates:

- Natural language can route into a structured companion action.
- The result is not only dialogue; the trap is actually disabled.
- Future trap-trigger checks read the changed state.

## 3. Lore Unlocks Negotiation Leverage

```text
Player: Read the chemical notes.
System: [线索整合] chemical_notes -> diary_context

Player: Read the necromancer diary.
System: The diary links Gribbo, the heavy iron key, and the poison defense.

State:
- act3_diary_context_gathered=true
- act3_diary_decoded=true
- act3_gribbo_potion_truth_known=true
```

What this demonstrates:

- Exploration creates information advantage.
- A later boss conversation can depend on what the player actually learned.
- The memory/state layer prevents this from being a one-off scripted line.

## 4. Multi-Agent Strategy Split

```text
Player: How should we handle him?

Astarion: Give me one chance and I can get the key out of his hand.
Shadowheart: Push too hard and the poison tanks may rupture first.
Lae'zel: Kill the gatekeeper. Take the key. Open the door.

Journal:
- [Boss方案] astarion -> steal_key
- [Boss方案] shadowheart -> contain_corruption
- [Boss方案] laezel -> execute
```

What this demonstrates:

- The party is not a single monolithic assistant.
- Each companion has a role, risk preference, and tactical agenda.
- The UI presents this as a readable bark queue rather than overlapping speech.

## 5. Truth Negotiation Produces A Real Item Transfer

```text
Player: I know what the potion did to you. You are not a guard. You are an experiment.
Give me the key and we will get you out.

Gribbo: Shut up! Gribbo is gatekeeper, not experiment! Not!

EventDrain:
- [Boss解决] negotiation -> key_surrendered
- [物品转移] gribbo -> player heavy_iron_key

State:
- act4_negotiation_success=true
- act4_heavy_iron_key_obtained=true
- player_inventory.heavy_iron_key=1
- gribbo.status=spared
```

What this demonstrates:

- Dialogue can cause gameplay consequences.
- Item transfer is committed through the event pipeline.
- The model does not silently mutate inventory through prose.

## 6. Memory Echo

```text
Earlier:
Player rebukes Astarion.

Later:
Player asks Astarion for help.

Astarion: Now you need me?

State:
- necromancer_lab_astarion_memory_echo_seen=true
- necromancer_lab_astarion_rebuke_echo_seen=true
```

What this demonstrates:

- Companion tone can depend on prior social choices.
- The memory echo is visible to the player without blocking the critical path.
- The system can express continuity without adding a large quest system.
