from __future__ import annotations

import copy
import random
import uuid

from .agent import Agent
from .genome import ALL_TOOLS, Genome
from .personality import Personality


def mutate_genome(genome: Genome, rate: float = 0.3) -> Genome:
    child = copy.deepcopy(genome)
    child.id = f"g-{uuid.uuid4().hex[:8]}"
    child.parent_id = genome.id
    child.generation = genome.generation + 1
    child.mutation_ops = []

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
        will_to_live=nudge(p.will_to_live),
    )


def crossover(a: Agent, b: Agent, generation: int) -> Agent:
    """Uniform crossover: each trait independently picked from one parent.

    Averaging traits (the old approach) collapses variance every generation —
    children drift toward the population mean and the gene pool converges to
    monoculture within ~50 generations. Uniform crossover preserves variance:
    a child inherits each trait verbatim from one parent, so distinctive
    lineages can persist long enough for selection to act on them. Mutation
    on top of that does the small-step exploration.

    Tools follow the same logic: if both parents have a tool, the child gets
    it (it's been selected for in both lineages). If only one parent has it,
    50/50 — so tool sets don't monotonically grow into "everyone has all tools."
    """
    def pick_trait(getter):
        return getter(a if random.random() < 0.5 else b)

    all_tools = set(a.genome.allowed_tools) | set(b.genome.allowed_tools)
    inherited_tools: list[str] = []
    for tool in all_tools:
        in_a = tool in a.genome.allowed_tools
        in_b = tool in b.genome.allowed_tools
        if in_a and in_b:
            inherited_tools.append(tool)
        elif random.random() < 0.5:
            inherited_tools.append(tool)
    # Viability floor: keep the existing >=2 tools invariant.
    if len(inherited_tools) < 2:
        leftovers = list(all_tools - set(inherited_tools))
        random.shuffle(leftovers)
        while len(inherited_tools) < 2 and leftovers:
            inherited_tools.append(leftovers.pop())

    genome = Genome(
        generation=generation,
        parent_id=f"{a.genome.id}x{b.genome.id}",
        allowed_tools=inherited_tools,
        speed_vs_thoroughness=pick_trait(lambda x: x.genome.speed_vs_thoroughness),
        risk_tolerance=pick_trait(lambda x: x.genome.risk_tolerance),
    )
    personality = Personality(
        curiosity=pick_trait(lambda x: x.personality.curiosity),
        aggression=pick_trait(lambda x: x.personality.aggression),
        caution=pick_trait(lambda x: x.personality.caution),
        sociability=pick_trait(lambda x: x.personality.sociability),
        creativity=pick_trait(lambda x: x.personality.creativity),
        will_to_live=pick_trait(lambda x: x.personality.will_to_live),
    )
    # Child scatters near the higher-fitness parent (~240 logical units, scaled with map).
    parent = a if a.fitness >= b.fitness else b
    return Agent(
        genome=mutate_genome(genome, rate=0.15),
        personality=mutate_personality(personality, rate=0.1),
        generation_born=generation,
        x=parent.x + random.gauss(0, 240.0),
        y=parent.y + random.gauss(0, 240.0),
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
