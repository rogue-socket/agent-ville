"""Synthetic fitness evaluation.

Tasks are drawn from a single global, biome-agnostic distribution — every
agent sees the same kind of work regardless of where it lives. The agent's
biome only modulates how richly that work pays: a thorough task in the
Forest pays better than the same thorough task in the Desert.

This decouples "can you do the task" (genome) from "where does it pay best"
(location). Selection acts on genuine genome-task competence first; biome is
a gradient on top, not the source of the answer. Lineages still specialize
spatially — a Desert-favored task pays much more in the Desert than the
Forest — but a competent agent in the wrong biome still scores better than
an incompetent one in the right biome.

Real fitness would come from running agents against actual tasks via LLM
calls. This module provides synthetic scoring so the evolution mechanics
work standalone.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .agent import Agent
from .environment import BIOME_RULES, Biome, biome_at
from .genome import ALL_TOOLS

TASK_TYPES = [
    "fix_bug", "add_feature", "refactor", "write_tests",
    "review_code", "optimize", "document", "debug",
]

# How strongly biome modulates the score on top of the base genome-task match.
# 0.0 = biome is decoration; 1.0 = biome can double or zero the score.
# 0.4 = up to ±40%: a real gradient that doesn't drown out genome quality.
BIOME_MOD_STRENGTH = 0.4


@dataclass
class Task:
    name: str
    ideal_speed: float          # 0-1
    ideal_thoroughness: float   # 0-1
    required_tools: list[str]
    risk_level: float           # 0-1

    @classmethod
    def random(cls) -> Task:
        """A globally-drawn task — same distribution everywhere."""
        ideal_speed = random.random()
        # Loosely anti-correlated with speed but free to deviate.
        ideal_thoroughness = max(0.0, min(1.0, (1.0 - ideal_speed) + random.gauss(0, 0.2)))
        return cls(
            name=random.choice(TASK_TYPES),
            ideal_speed=ideal_speed,
            ideal_thoroughness=ideal_thoroughness,
            required_tools=random.sample(ALL_TOOLS, k=random.randint(1, 3)),
            risk_level=random.random(),
        )


def evaluate(agent: Agent, task: Task) -> float:
    """Score how well an agent's genome fits a task. Returns 0-1.

    Pure genome-task match — biome plays no role here.
    """
    g = agent.genome
    p = agent.personality

    # Speed/thoroughness alignment (agent's speed pref vs task's ideal)
    speed_fit = 1.0 - abs(g.speed_vs_thoroughness - task.ideal_speed)
    thorough_fit = 1.0 - abs((1 - g.speed_vs_thoroughness) - task.ideal_thoroughness)

    # Tool coverage — does the agent have the tools the task needs?
    needed = set(task.required_tools)
    has = set(g.allowed_tools)
    tool_score = len(needed & has) / len(needed) if needed else 1.0

    # Risk alignment — risk-tolerant agents handle risky tasks, risk-averse handle safe ones.
    # Uses the genome's risk_tolerance (a strategy trait), not personality.caution (a behavior trait).
    risk_fit = 1.0 - abs(g.risk_tolerance - task.risk_level)

    # Personality bonus — curiosity and creativity give a small edge
    personality_bonus = (p.curiosity * 0.05 + p.creativity * 0.05)

    # Random noise to simulate real-world variance
    noise = random.gauss(0, 0.05)

    raw = (
        speed_fit * 0.25
        + thorough_fit * 0.20
        + tool_score * 0.25
        + risk_fit * 0.15
        + personality_bonus
        + noise
    )
    return max(0.0, min(1.0, raw))


def biome_multiplier(biome: Biome, task: Task) -> float:
    """Reward multiplier for doing this task in this biome.

    A biome whose preferences align with the task's demands pays a bonus;
    one that fights the task pays a penalty. Bounded by BIOME_MOD_STRENGTH so
    genome quality remains the dominant fitness signal.
    """
    rules = BIOME_RULES[biome]
    speed_align = 1.0 - 2 * abs(rules.speed_pref - task.ideal_speed)
    thorough_align = 1.0 - 2 * abs(rules.thorough_pref - task.ideal_thoroughness)
    needed = set(task.required_tools)
    if needed:
        tool_align = 2 * (len(set(rules.tool_pool) & needed) / len(needed)) - 1
    else:
        tool_align = 0.0
    alignment = (speed_align + thorough_align + tool_align) / 3.0
    return 1.0 + BIOME_MOD_STRENGTH * alignment


def evaluate_batch(agent: Agent, n_tasks: int = 3) -> float:
    """Score an agent on globally-drawn tasks; biome modulates the reward."""
    biome = biome_at(agent.x, agent.y)
    scores: list[float] = []
    for _ in range(n_tasks):
        task = Task.random()
        base = evaluate(agent, task)
        scores.append(max(0.0, min(1.0, base * biome_multiplier(biome, task))))
    return sum(scores) / len(scores)
