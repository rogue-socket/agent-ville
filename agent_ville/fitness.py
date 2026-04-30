"""Synthetic fitness evaluation.

Real fitness would come from running agents against actual tasks via LLM calls.
This module provides synthetic scoring so the evolution mechanics work standalone.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .agent import Agent
from .genome import ALL_TOOLS


@dataclass
class Task:
    name: str
    ideal_speed: float          # 0-1
    ideal_thoroughness: float   # 0-1
    required_tools: list[str]
    risk_level: float           # 0-1

    @classmethod
    def random(cls) -> Task:
        task_types = [
            "fix_bug", "add_feature", "refactor", "write_tests",
            "review_code", "optimize", "document", "debug",
        ]
        n_tools = random.randint(1, 4)
        return cls(
            name=random.choice(task_types),
            ideal_speed=random.random(),
            ideal_thoroughness=random.random(),
            required_tools=random.sample(ALL_TOOLS, k=n_tools),
            risk_level=random.random(),
        )


def evaluate(agent: Agent, task: Task) -> float:
    """Score how well an agent's genome fits a task. Returns 0-1."""
    g = agent.genome
    p = agent.personality

    # Speed/thoroughness alignment (agent's speed pref vs task's ideal)
    speed_fit = 1.0 - abs(g.speed_vs_thoroughness - task.ideal_speed)
    thorough_fit = 1.0 - abs((1 - g.speed_vs_thoroughness) - task.ideal_thoroughness)

    # Tool coverage — does the agent have the tools the task needs?
    needed = set(task.required_tools)
    has = set(g.allowed_tools)
    tool_score = len(needed & has) / len(needed) if needed else 1.0

    # Risk alignment — cautious agents do well on risky tasks, aggressive on safe ones
    risk_fit = 1.0 - abs(p.caution - task.risk_level)

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


def evaluate_batch(agent: Agent, n_tasks: int = 3) -> float:
    """Run an agent against multiple random tasks, return mean fitness."""
    tasks = [Task.random() for _ in range(n_tasks)]
    scores = [evaluate(agent, t) for t in tasks]
    return sum(scores) / len(scores)
