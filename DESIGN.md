# Agent-Ville — Design

This document captures the design committed to during the 14-question grilling session. It supersedes the simpler model in the current code. The existing code in `agent_ville/` is the prototype that taught us what to build; this is what to build next.

## Premise

Agent-Ville is a single very-long-running sandbox simulation. The goal is to explore what kinds of agents flourish under different world conditions, not to demonstrate evolutionary mechanics in the abstract.

Three goals at once. The primary goal is **sandbox-tinkering** — a place to add mechanics that compound. The secondary goals are **phenomena visibility** (you can see evolutionary dynamics happening) and **legibility** (someone loading the page can read what the agents are doing). New mechanics should support all three.

The README's larger vision (LLM-scored coding agents, capsule isolation, evolution registry) is **not the goal here**. That's a different project. This stays a self-contained simulation.

## The world

- **Spatial**, and the simulation owns position. Agents have `(x, y)` as first-class state. The canvas reads positions from the sim, not the other way around.
- **Tile grid**, fixed dimensions, single hand-authored map. Each tile carries a `biome`.
- **No time-varying environment** in the initial build. The map is constant. Time-varying conditions (climate cycles, blights, hotspots that migrate) are a deliberately deferred future layer.
- **Boundary**: reflective (bounce). Wrap-around (torus) was rejected — it undoes the regional structure the biome arrangement is trying to create.

### Biome palette (5–6, target 6)

| Biome | Tone | Rewards | Tools needed |
|---|---|---|---|
| Forest | dark green | caution + thoroughness | read, analyze |
| Desert | ochre | aggression + speed | execute, search |
| Marsh | dusty purple | creativity + risk | write, communicate |
| Coast | pale teal | sociability | communicate, search |
| Tundra | pale blue | curiosity + thoroughness | search, analyze |
| Plains | pale tan | neutral refuge | any |

If reduced to 5, drop Tundra (curiosity is partially covered by Marsh). Biome tones are intentionally low-saturation so personality-colored agents pop against them.

### Biome fitness coupling

Tasks (existing `fitness.py`) are still drawn per agent per generation, but their **parameters are sampled from a biome-specific distribution**. Forest tasks demand thoroughness and need `read`/`analyze`; Desert tasks demand speed and need `execute`/`search`; etc. The existing `evaluate()` logic is unchanged; only `Task.random()` becomes `Task.random_for_biome(biome)`. This is the mechanism that makes `allowed_tools` and trait alignment finally matter visibly — lineages without the right tools get culled out of their biome.

## The simulation loop

### Single long run

There is exactly one run, intended to go for very long. This rules out per-run procedural map variation and motivates real persistence.

### Persistence

- **Periodic JSON snapshot** to disk. Cadence: every ~60 generations or ~60 seconds of wall clock, whichever rarer.
- Atomic write (`.tmp` + `os.replace`). Single file, human-readable.
- Format mirrors the existing `to_dict()` methods, extended for the new layers. `from_dict()` constructors with default-on-missing-field semantics for forward compatibility.
- Snapshot carries a `version` field; loaders branch on it.

### Retention (bounded growth)

`graveyard`, `events`, and `stats_history` are append-only and will dominate memory at ~100k generations.

- `events`: rolling cap at last ~10k.
- `stats_history`: rolling cap at last ~1k.
- `graveyard`: keep agent dicts for last ~10k deaths; older deaths summarized to aggregate stats only.
- **Lineage edges** (parent→child with generation and final flourishing) preserved indefinitely as a separate append-only TSV. Small, and the one thing you'll regret throwing away.

### Two cadences

- **Generation**: selection, mating, task evaluation, stats. The current `Village.step()`'s job.
- **Motion tick**: per-agent position update, need depletion, biography accrual, event detection. Multiple motion ticks per generation (recommendation: 20, open).

## The agent

An agent is no longer a flat dataclass. It has **five layers**.

### Layer 1 — The given (genome + personality)

`Genome` and `Personality` retain their current shape. The change: **`Personality` becomes mutable through life** via personality drift driven by biographical events. `Genome` remains immutable post-spawn; it mutates only at reproduction.

### Layer 2 — The present (psyche)

The agent has a `Psyche`, an interface. Three concrete implementations:

- **`ERG`** — 3 needs: Existence, Relatedness, Growth.
- **`MaslowSim`** — 5 needs: Body, Safety, Belonging, Esteem, Becoming.
- **`Sixfold`** — 6 needs: Body, Safety, Belonging, Esteem, Becoming, Beyond.

Each architecture exposes:

```
Psyche (interface)
  update(world_ctx, biography)      — tick each need
  dominant_pursuit() -> Goal        — current behavioral driver
  flourishing() -> float in [0,1]   — canonical projection for cross-arch comparison
  mate_signature() -> NeedKey       — what this agent needs from a partner
  in_despair() -> bool              — drives despair-death pathway
```

**Tradeoff:** richer architectures have higher flourishing ceilings and more ways to suffer. ERG agents flourish more cheaply but have no Beyond dimension. Sixfold agents have higher upside but carry an unmet Beyond need when conditions don't support it.

Needs are **simultaneously active**. Urgency per need: `(1 − satisfaction) × weight`. Weights are **personality-modulated**: sociable agents weight Belonging higher; curious weight Becoming higher; cautious weight Safety. The **dominant urgency** (single highest-urgency need each tick) drives behavior. Others continue updating; they just don't steer this tick.

**Regression**: sustained Body or Safety below threshold for *N* consecutive ticks **collapses architecture downward** one level. Sixfold→MaslowSim→ERG. Discarded needs are no longer tracked or pursued. Permanent unless reversed.

**Expansion**: sustained high flourishing in a richer-than-self social context can shift architecture upward. Rare. Asymmetric with regression by design: narrowing is easier than broadening.

### Layer 3 — The history (biography)

Three sub-layers, each with a distinct job.

**Trigger buffer** — ring buffer, last ~20 ticks of `(need_satisfactions, biome_id, fitness)`. Sole purpose: regression/expansion detection. Cheap, bounded, no semantic content.

**Event log** — capped at ~30 entries. Indelible events are protected from eviction (lowest-weight evicted first). 12 event types:

1. mate-found (joyful, slow decay)
2. mate-lost (painful, indelible-low-floor)
3. child-born (joyful, indelible-low-floor)
4. child-died (painful, indelible-mid-floor) — strongest scar
5. kin-died-witnessed (painful, indelible-low-floor)
6. stranger-died-witnessed (painful, normal decay)
7. despair-episode (painful, indelible-mid-floor) — regression itself becomes memory
8. awakening (joyful, indelible-high-floor) — expansion event
9. migration (neutral-mild, fast decay)
10. conflict (signed valence by outcome)
11. aid-given-to-non-kin (joyful, slow decay) — Beyond-feeding
12. aid-received-from-non-kin (joyful, slow decay)

Each event: `(tick, type, others_involved, valence, weight, decay_rate, floor)`.

**Life-phase aggregates** — five phases by age fraction: infancy (0–0.1), childhood (0.1–0.25), adolescence (0.25–0.4), adulthood (0.4–0.8), elderhood (0.8–1.0). Each phase frozen at end. Each summary: `avg_flourishing`, `dominant_pursuit`, `num_significant_events`, `net_valence`, `biome_dwelt_in_most`. Used for inspection (hover tooltip) and identity readout.

### Layer 4 — The context (world + others)

The agent is shaped each tick by:

- The biome of its current tile (passive fitness modulation, motion modulation).
- Other agents within local radii — for mating proximity, crowd-seek/avoid forces, witness (esteem feeding), aid (Beyond feeding for both parties), conflict, and adolescent imprinting on local modal architecture.

### Layer 5 — The end (mortality)

Multiple death pathways:

- **Body = 0**: starvation. Acute.
- **Sustained Safety = 0**: collapse. Slower.
- **Sustained Belonging = 0** (in architectures that include it): despair. Slowest.
- **Age > max_age**: natural. Background rate.
- (Future: conflict-induced death; self-sacrifice for Beyond.)

## Motion model

Four layered force contributions, summed per motion tick.

1. **Brownian drift** — small random impulse, magnitude scaled by curiosity.
2. **Personality bias** — directional tendency derived from traits (sociable pulled to crowds, curious pushed outward, cautious stays still).
3. **Goal force** — vector toward the target of the dominant pursuit. Targets include: mate-seek, biome-fit-seek (gradient ascent on local fitness landscape, 5-tile radius), crowd-seek/avoid, kin-seek, witness-seek (to feed Esteem), teach-seek (for elder agents feeding Beyond).
4. **Biome-modulated motion** — Marsh slows everyone, Coast attracts sociable agents, Forest is sticky for cautious agents, etc.

Net update: `v_{t+1} = damping × v_t + sum(forces)`, then `pos += v`. Damping (~0.9) kills the runaway velocity bug currently present in `app.js`. Boundary handling: reflective.

The four-layer motion model is rich. Each layer should be a small isolated function so they can be tuned independently.

## Mating

- **Proximity required**: `mating_radius ~8 tiles`. Replaces the existing random-from-top-half logic.
- **Compatibility is pluralistic, not fitness-rank**: vector match against the agent's `mate_signature()` (architecture-specific) plus biographical resonance — agents drawn to mates whose event-valence profile is similar.
- **Birth position**: random scatter within radius ~3 of the higher-fitness parent. Lineage neighborhoods form, with permeable boundaries.
- **Generation 0 spawn**: biome-uniform — 2–3 founders per biome. Mixed-random destroys initial biome differentiation; one-corner is too slow to spread.
- **Child architecture**: inherits the higher-fitness parent's `Psyche` as default. Adolescent imprinting may override based on local modal architecture among neighbors.

## Selection

"Fitness" as a scalar is **vestigial**. Selection acts on **flourishing area-under-curve** combined with reproduction success (descendants who reach reproductive age and themselves flourish).

Tasks still exist, reframed as **the world's friction**: competence on tasks feeds Body satisfaction (the "earn your keep" coupling). Eventually, tasks become biome-conditioned (above).

## Revised generation step

```
For each generation:
  For each motion_tick in range(N):
    For each living agent:
      Update needs (depletion + environmental + biographical influences)
      Determine dominant urgency
      Compute forces (brownian + personality + goal + biome)
      Update velocity, position
      Detect events; append to trigger buffer; append to event log if significant
      Update biography (trigger buffer always; event log on event)

  For each living agent (end of generation):
    Evaluate biome-conditioned tasks
      → competence feeds Body (and witnessed-by-nearby feeds Esteem)
    Age up; check natural death; check despair pathway
    Check regression / expansion triggers; if fired, swap psyche architecture
    If in adolescence: probabilistic architecture shift toward local mode
    Apply personality drift from new events

  Selection: pluralistic — high-flourishing agents with compatible mates reproduce
  Reproduction: crossover + mutation; child placed near parent
  Update stats; emit snapshot if cadence reached
```

## Visualization expectations

- Background: tiled biome colors (low saturation).
- Agents: circle whose **hue** encodes architecture (3 colors — ERG / MaslowSim / Sixfold) and whose **brightness** encodes current flourishing. Size encodes age.
- Hover tooltip: architecture, current dominant pursuit, current need vector, top 3 biographical events, life-phase narrative.
- The canvas polls `/api/state` at 800ms but motion happens at higher tick rate — client-side interpolation may be required between snapshots, or move to a higher poll rate. Open sub-fork.

## Open sub-forks

These are touched but not landed. Listed in priority order.

1. **Mating compatibility across architectures.** When ERG mates with Sixfold, what does the child get and what does Esteem-need-from-mate even mean for an ERG agent who has no Esteem dimension? Recommended starting point: child takes higher-fitness parent's architecture; partial compatibility match between architectures via a projection function (ERG.Relatedness ≈ MaslowSim.Belonging + 0.5×MaslowSim.Esteem).
2. **Witness mechanism for Esteem.** Esteem feeds on being witnessed performing competently by nearby others. Mechanically: when an agent's task evaluation completes, nearby agents act as witnesses; both witness and performer get a small Esteem boost. Open: radius, magnitude, kinship requirement.
3. **Aid mechanism for Beyond.** What concrete tick-level act feeds Beyond? Recommendation: an elder agent within proximity of a young agent, with elder in "teach-seek" pursuit, transfers an architecture-bias and small need-boosts to the young, satisfying its own Beyond. Open: bandwidth, kinship requirement, mortality cost.
4. **Despair death timescales.** Exact thresholds and tick counts for each pathway. Needs play-testing.
5. **Personality drift magnitudes per event type.** How much does a child-death move caution? Needs calibration.
6. **Adolescent imprinting math.** Exact formula for "shift probability toward local modal architecture per tick." Starting point: `p = (1 − match) × sociability × 0.01` per tick during adolescence window (life-tick ages 1–3 of typical lifespan).
7. **Cross-architecture flourishing projection.** `flourishing()` returns a scalar in [0,1] for selection ranking. Starting point: weighted mean of available need-satisfactions, normalized to the architecture's max possible.
8. **Conflict mechanics.** Currently un-modeled. Aggression trait exists but does nothing. Open: does the sim have agent-vs-agent conflict with real costs (resource competition, fight outcomes affecting Body/Safety)?
9. **Motion ticks per generation.** Starting point: 20. Worth thinking about in context of canvas polling.
10. **Snapshot schema versioning.** `version` field on snapshot; `from_dict` constructors with default-on-missing-field semantics.
11. **UI overlay specifics.** Hover content, color encoding, optional debug overlay showing per-agent force vectors.
12. **Time-varying environment.** Deferred. Eventually layer on biome shifts, climate cycles, hotspots.

## Scope assessment

This is roughly a **6-month rewrite** if pursued seriously. The existing ~500 lines become the rendering substrate and HTTP scaffolding; ~80% of the code is new. Each design decision selected the richest of the options on the table, and they compound. Treat this as a new project that reuses the prototype's loop and viz, not as an extension of the prototype.

## Recommended build order

1. **Spatial substrate.** Add `(x, y)` to `Agent`. Render tiles. Add reflective boundary, basic motion (start with brownian only). Verify the spatial dynamics work with the *existing* fitness function.
2. **Biome map and conditional tasks.** Hand-author the single map. Implement `Task.random_for_biome()`. Watch lineages specialize spatially under the existing personality/genome model.
3. **Personality-driven motion + birth scatter.** Add the personality bias and goal forces layer by layer. Add proximity-mating. At this point the sim is recognizably different from the prototype but still uses the old fitness model.
4. **Persistence.** Snapshot + lineage TSV before adding more state. Forces the schema discipline you'll need later.
5. **Psyche layer.** Start with `Sixfold` only. Add need depletion, dominant urgency, regression. No architecture diversity yet.
6. **Biography layer.** Trigger buffer first, then event log, then phase aggregates. Wire personality drift.
7. **Architecture diversity.** Add `ERG` and `MaslowSim`. Add adolescent imprinting and expansion pathway.
8. **Beyond mechanics.** Aid, teaching, legacy.
9. **Visualization upgrades.** Hover tooltips, color encoding, narrative rendering.
10. **Time-varying environment** if/when the static world stops being interesting.

Each step should produce a working sim with observably more behavior than the previous one. If a step doesn't pay back in visible behavior, stop before adding the next layer.
