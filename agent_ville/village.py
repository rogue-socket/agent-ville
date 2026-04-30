from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .agent import Agent
from .evolution import crossover, mutate_genome, mutate_personality, select_survivors
from .fitness import evaluate_batch


@dataclass
class Event:
    generation: int
    kind: str       # birth, death, mutation, immigration
    agent_name: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "kind": self.kind,
            "agent_name": self.agent_name,
            "detail": self.detail,
        }


class Village:
    def __init__(
        self,
        population_size: int = 15,
        max_population: int = 30,
        min_population: int = 5,
    ):
        self.target_pop = population_size
        self.max_population = max_population
        self.min_population = min_population
        self.generation = 0
        self.agents: list[Agent] = [Agent.spawn(0) for _ in range(population_size)]
        self.graveyard: list[Agent] = []
        self.events: list[Event] = []
        self.stats_history: list[dict[str, Any]] = []

        # Log initial births
        for a in self.agents:
            self.events.append(Event(0, "birth", a.name, "spawned in generation 0"))

    def step(self) -> list[Event]:
        """Advance one generation. Returns new events."""
        self.generation += 1
        new_events: list[Event] = []

        # 1. Evaluate fitness for living agents
        alive = [a for a in self.agents if a.alive]
        for agent in alive:
            score = evaluate_batch(agent, n_tasks=3)
            agent.fitness_history.append(score)

        # 2. Age all living agents
        for agent in alive:
            cause = agent.age_up()
            if cause:
                new_events.append(Event(
                    self.generation, "death", agent.name,
                    f"died of {cause} at age {agent.age}",
                ))

        # 3. Kill lowest-fitness agents if overpopulated
        alive = [a for a in self.agents if a.alive]
        if len(alive) > self.max_population:
            survivors = select_survivors(alive, self.target_pop)
            killed = set(id(a) for a in alive) - set(id(a) for a in survivors)
            for agent in alive:
                if id(agent) in killed:
                    agent.alive = False
                    agent.cause_of_death = "selection"
                    new_events.append(Event(
                        self.generation, "death", agent.name,
                        f"eliminated by selection (fitness {agent.fitness:.2f})",
                    ))

        # 4. Reproduce — top agents produce offspring
        alive = [a for a in self.agents if a.alive]
        births_needed = max(0, self.target_pop - len(alive))

        if len(alive) >= 2:
            # Sort by fitness for mating pool
            ranked = sorted(alive, key=lambda a: a.fitness, reverse=True)
            top = ranked[: max(2, len(ranked) // 2)]

            for _ in range(births_needed):
                parents = random.sample(top, k=2)
                child = crossover(parents[0], parents[1], self.generation)
                self.agents.append(child)
                new_events.append(Event(
                    self.generation, "birth", child.name,
                    f"born from {parents[0].name} x {parents[1].name}",
                ))
        elif births_needed > 0:
            # Not enough agents to crossover — spontaneous generation
            for _ in range(births_needed):
                child = Agent.spawn(self.generation)
                self.agents.append(child)
                new_events.append(Event(
                    self.generation, "immigration", child.name,
                    "arrived as immigrant",
                ))

        # 5. Occasional random immigrant (genetic diversity)
        alive_count = sum(1 for a in self.agents if a.alive)
        if random.random() < 0.1 and alive_count < self.max_population:
            immigrant = Agent.spawn(self.generation)
            self.agents.append(immigrant)
            new_events.append(Event(
                self.generation, "immigration", immigrant.name,
                "arrived as immigrant",
            ))

        # 6. Move dead to graveyard
        newly_dead = [a for a in self.agents if not a.alive and a not in self.graveyard]
        self.graveyard.extend(newly_dead)

        # 7. Record stats
        alive = [a for a in self.agents if a.alive]
        if alive:
            fitnesses = [a.fitness for a in alive]
            self.stats_history.append({
                "generation": self.generation,
                "population": len(alive),
                "avg_fitness": round(sum(fitnesses) / len(fitnesses), 3),
                "max_fitness": round(max(fitnesses), 3),
                "min_fitness": round(min(fitnesses), 3),
                "total_deaths": len(self.graveyard),
            })

        self.events.extend(new_events)
        return new_events

    def get_state(self) -> dict[str, Any]:
        alive = [a for a in self.agents if a.alive]
        return {
            "generation": self.generation,
            "agents": [a.to_dict() for a in alive],
            "graveyard_size": len(self.graveyard),
            "recent_dead": [a.to_dict() for a in self.graveyard[-5:]],
            "events": [e.to_dict() for e in self.events[-30:]],
            "stats_history": self.stats_history[-50:],
        }
