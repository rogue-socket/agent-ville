from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

ALL_TOOLS = ["read", "write", "search", "execute", "analyze", "communicate"]


@dataclass
class Genome:
    id: str = field(default_factory=lambda: f"g-{uuid.uuid4().hex[:8]}")
    parent_id: str | None = None
    generation: int = 0

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
            allowed_tools=random.sample(ALL_TOOLS, k=random.randint(2, len(ALL_TOOLS))),
            speed_vs_thoroughness=random.random(),
            risk_tolerance=random.random(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "generation": self.generation,
            "allowed_tools": self.allowed_tools,
            "speed_vs_thoroughness": round(self.speed_vs_thoroughness, 3),
            "risk_tolerance": round(self.risk_tolerance, 3),
            "mutation_ops": self.mutation_ops,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Genome:
        # default-on-missing-field for forward compatibility across snapshot versions
        return cls(
            id=d.get("id", f"g-{uuid.uuid4().hex[:8]}"),
            parent_id=d.get("parent_id"),
            generation=d.get("generation", 0),
            allowed_tools=list(d.get("allowed_tools", list(ALL_TOOLS))),
            speed_vs_thoroughness=d.get("speed_vs_thoroughness", 0.5),
            risk_tolerance=d.get("risk_tolerance", 0.5),
            mutation_ops=list(d.get("mutation_ops", [])),
        )
