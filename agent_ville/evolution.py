from __future__ import annotations

import copy
import random
import uuid

from .agent import Agent
from .genome import ALL_TOOLS, STYLES, Genome
from .personality import Personality


def mutate_genome(genome: Genome, rate: float = 0.3) -> Genome:
    child = copy.deepcopy(genome)
    child.id = f"g-{uuid.uuid4().hex[:8]}"
    child.parent_id = genome.id
    child.generation = genome.generation + 1
    child.mutation_ops = []

    if random.random() < rate:
        child.style = random.choice(STYLES)
        child.mutation_ops.append(f"style->{child.style}")

    if random.random() < rate:
        delta = random.gauss(0, 0.1)
        child.speed_vs_thoroughness = max(0, min(1, child.speed_vs_thoroughness + delta))
        child.mutation_ops.append(f"speed+={delta:.3f}")

    if random.random() < rate:
        delta = random.gauss(0, 0.1)
        child.risk_tolerance = max(0, min(1, child.risk_tolerance + delta))
        child.mutation_ops.append(f"risk+={delta:.3f}")

    # Tool mutations are rarer
    if random.random() < rate * 0.5:
        if len(child.allowed_tools) > 2:
            tool = random.choice(child.allowed_tools)
            child.allowed_tools.remove(tool)
            child.mutation_ops.append(f"-tool:{tool}")
        else:
            available = [t for t in ALL_TOOLS if t not in child.allowed_tools]
            if available:
                tool = random.choice(available)
                child.allowed_tools.append(tool)
                child.mutation_ops.append(f"+tool:{tool}")

    return child


def mutate_personality(p: Personality, rate: float = 0.2) -> Personality:
    def nudge(val: float) -> float:
        if random.random() < rate:
            return max(0.0, min(1.0, val + random.gauss(0, 0.15)))
        return val

    return Personality(
        curiosity=nudge(p.curiosity),
        aggression=nudge(p.aggression),
        caution=nudge(p.caution),
        sociability=nudge(p.sociability),
        creativity=nudge(p.creativity),
    )


def crossover(a: Agent, b: Agent, generation: int) -> Agent:
    """Blend two parent agents into an offspring."""
    genome = Genome(
        generation=generation,
        parent_id=f"{a.genome.id}x{b.genome.id}",
        style=random.choice([a.genome.style, b.genome.style]),
        allowed_tools=list(set(a.genome.allowed_tools) | set(b.genome.allowed_tools)),
        speed_vs_thoroughness=(a.genome.speed_vs_thoroughness + b.genome.speed_vs_thoroughness) / 2,
        risk_tolerance=(a.genome.risk_tolerance + b.genome.risk_tolerance) / 2,
    )
    personality = Personality(
        curiosity=(a.personality.curiosity + b.personality.curiosity) / 2,
        aggression=(a.personality.aggression + b.personality.aggression) / 2,
        caution=(a.personality.caution + b.personality.caution) / 2,
        sociability=(a.personality.sociability + b.personality.sociability) / 2,
        creativity=(a.personality.creativity + b.personality.creativity) / 2,
    )
    return Agent(
        genome=mutate_genome(genome, rate=0.15),
        personality=mutate_personality(personality, rate=0.1),
        generation_born=generation,
    )


def select_survivors(agents: list[Agent], keep: int) -> list[Agent]:
    """Tournament selection — pick the fittest survivors."""
    alive = [a for a in agents if a.alive]
    if len(alive) <= keep:
        return alive

    selected: list[Agent] = []
    pool = list(alive)
    for _ in range(keep):
        contenders = random.sample(pool, k=min(3, len(pool)))
        winner = max(contenders, key=lambda a: a.fitness)
        selected.append(winner)
        pool.remove(winner)
    return selected
