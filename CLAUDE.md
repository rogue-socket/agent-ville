# Agent-Ville

## What this is

A self-contained simulation of AI agents evolving through Darwinian natural selection. Agents have genomes (style, tools, speed/risk traits) and personalities (curiosity, aggression, caution, sociability, creativity). Each generation they're scored on tasks, aged, selected, and reproduced with mutations.

## Running

```bash
python3 -m agent_ville     # starts server at http://localhost:8420
```

No external dependencies — pure Python stdlib + vanilla JS.

## Architecture

```
agent_ville/
  genome.py        # Genome dataclass — the "DNA"
  personality.py   # 5-trait personality vector
  agent.py         # Agent with lifecycle, fitness history
  evolution.py     # Mutation, crossover, tournament selection
  fitness.py       # Synthetic fitness scoring (placeholder for LLM)
  village.py       # Population manager, generation loop
  simulation.py    # HTTP server + background sim thread
  __main__.py      # Entry point
web/
  index.html       # Canvas-based visualization
  style.css        # Dark theme
  app.js           # Rendering, polling, interaction
```

## Key patterns

- Village.step() is the core loop: evaluate → age → select → reproduce → immigrate
- Fitness is currently synthetic (random tasks scored against genome traits). The real evolution happens when this is wired to LLM-powered task execution.
- The server uses stdlib http.server with a background thread for the sim loop and a threading lock for shared state.
- Frontend polls /api/state every 800ms. Agents are rendered on canvas with personality-based colors and fitness-based sizes.

## Known issues

See GitHub issues. Main bugs: canvas transform accumulation on resize, velocity runaway for curious agents, dead agents never removed from self.agents list.
