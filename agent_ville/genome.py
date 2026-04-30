from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

STYLES = ["cautious", "balanced", "aggressive", "analytical", "creative"]
ALL_TOOLS = ["read", "write", "search", "execute", "analyze", "communicate"]


@dataclass
class Genome:
    id: str = field(default_factory=lambda: f"g-{uuid.uuid4().hex[:8]}")
    parent_id: str | None = None
    generation: int = 0

    # Prompt profile
    style: str = "balanced"
    constraints: list[str] = field(default_factory=list)

    # Tool profile
    allowed_tools: list[str] = field(default_factory=lambda: list(ALL_TOOLS))

    # Strategy profile
    speed_vs_thoroughness: float = 0.5  # 0 = thorough, 1 = fast
    risk_tolerance: float = 0.5

    # Mutation tracking
    mutation_ops: list[str] = field(default_factory=list)

    @classmethod
    def random(cls, generation: int = 0) -> Genome:
        return cls(
            generation=generation,
            style=random.choice(STYLES),
            allowed_tools=random.sample(ALL_TOOLS, k=random.randint(2, len(ALL_TOOLS))),
            speed_vs_thoroughness=random.random(),
            risk_tolerance=random.random(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "generation": self.generation,
            "style": self.style,
            "allowed_tools": self.allowed_tools,
            "speed_vs_thoroughness": round(self.speed_vs_thoroughness, 3),
            "risk_tolerance": round(self.risk_tolerance, 3),
            "mutation_ops": self.mutation_ops,
        }
