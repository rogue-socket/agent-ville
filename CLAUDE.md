# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-contained simulation of AI agents evolving through Darwinian natural selection. Agents have a `Genome` (allowed_tools, speed_vs_thoroughness, risk_tolerance) and a `Personality` (curiosity, aggression, caution, sociability, creativity, will_to_live). Each generation they're scored on tasks, aged, selected, and reproduced with mutations.

Fitness is currently **synthetic** (random tasks scored against genome traits in `fitness.py`). The real evolution happens when this is wired to LLM-powered task execution — the scaffolding (population, selection, crossover, mutation) is the part that's actually built.

> **Where the project is going:** see `DESIGN.md` at the repo root for the full target design (spatial substrate, biome map, multi-architecture `Psyche` layer, biography, developmental dynamics). The current code is the prototype; `DESIGN.md` is what to build next, with locked decisions and open sub-forks listed.

## Running

```bash
python3 -m agent_ville     # starts server at http://localhost:8420
```

- **Requires** Python 3.11+ (uses `from __future__ import annotations` + PEP 604 unions)
- **No dependencies** — pure Python stdlib + vanilla JS
- No test suite, no linter, no build step configured

## Architecture

```
agent_ville/
  genome.py        # Genome dataclass — the "DNA" (tools, speed, risk)
  personality.py   # 6-trait personality vector + HSL hue mapping for viz
  agent.py         # Agent: lifecycle, fitness_history, max_age (scales with fitness), to_snapshot/from_snapshot
  evolution.py     # mutate_genome, mutate_personality, crossover (uniform per-trait), select_survivors
  fitness.py       # Synthetic Task generation + scoring (global tasks, biome modulates reward)
  environment.py   # Biome map + motion physics constants
  village.py       # Village.step() — the generation loop; tracks events + stats_history; cadenced snapshot
  persistence.py   # LineageLog (append-only TSV) + save_snapshot/load_snapshot (atomic JSON)
  simulation.py    # HTTPServer + background sim thread + /api/* endpoints; auto-resumes from snapshot
  __main__.py      # Entry point
data/              # Created on first run; gitignored. lineage.tsv + snapshot.json live here.
web/
  index.html, style.css, app.js   # Canvas viz, polls /api/state every 800ms
```

## Key patterns

- **`Village.step()` is the core loop**: evaluate fitness → age all → continuous cull (`CULL_FRACTION` of eligible by lowest fitness, with a grace period for new agents) → overcrowding backstop (tournament if over `max_population`) → reproduce via `crossover` of top half (proximity-required) → ~10% chance of immigrant → move dead to graveyard → record stats. Population targets: `population_size=150`, `max=300`, `min=60`.
- **Fitness is a rolling mean** of the last 5 scores (`Agent.fitness` property), not cumulative. Agents need ≥1 generation of evaluation before they have any fitness.
- **`max_age` is fitness-driven**: `8 + int(fitness * 12)`, so high-performing agents live longer (range [8, 20]). New agents start at the floor and extend it as their fitness history fills in; a fitness collapse can shorten max_age below current age, killing the agent immediately. Death causes: `old_age`, `selection`.
- **Threading model**: `simulation.py` runs `simulation_loop` in a daemon thread; all mutations of `Village` go through `SimulationState._lock`. If you add new state mutations, wrap them in the lock.
- **HTTP API** (handled in `simulation.py`):
  - `GET /api/state` — full village snapshot (agents, recent events, last 50 stats)
  - `POST /api/step` — advance one generation
  - `POST /api/toggle` — play/pause the background loop
  - `POST /api/speed?=<float>` — clamped to [0.1, 10.0] gens/sec
- **Web frontend** is served as static files from `web/` by `SimpleHTTPRequestHandler`. No bundler; edit and reload.
- **IDs**: `Agent.id` is `a-<hex8>`, `Genome.id` is `g-<hex8>`. Crossover sets `parent_id` to `"<a>x<b>"`.

## Known issues (per README + project notes)

- Canvas transform accumulation on resize
- Velocity runaway for high-curiosity agents
- Dead agents are kept in `Village.agents` (only moved to `graveyard` after `step()` finishes the generation in which they died) — filter on `a.alive` when iterating

## Working in this repo

- The vision (LLM-driven variant factory, capsule isolation, evolution registry) is described in `README.md`. The current code is the population-scaffolding piece only — wiring real LLM-scored fitness is the next major increment.
- Surgical edits: the modules are small and each file owns a clear concept. New behaviors usually slot into `evolution.py`, `fitness.py`, or `village.py` rather than needing new files.
