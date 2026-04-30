from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from .genome import Genome
from .personality import Personality

NAMES = [
    "Ada", "Alan", "Alice", "Ava", "Basil", "Bea", "Cass", "Clay",
    "Dane", "Dara", "Echo", "Eli", "Faye", "Finn", "Gaia", "Glen",
    "Hale", "Iris", "Ivan", "Jade", "Juno", "Kai", "Kira", "Lars",
    "Lena", "Luna", "Milo", "Nara", "Nero", "Nova", "Odin", "Orla",
    "Otto", "Pax", "Pia", "Quinn", "Raya", "Reed", "Rhea", "Rio",
    "Sage", "Seth", "Skye", "Sol", "Tara", "Thea", "Vale", "Vera",
    "Wren", "Xara", "Yara", "Zara", "Zeke", "Zion",
]


@dataclass
class Agent:
    id: str = field(default_factory=lambda: f"a-{uuid.uuid4().hex[:8]}")
    name: str = ""
    genome: Genome = field(default_factory=Genome)
    personality: Personality = field(default_factory=Personality.random)
    age: int = 0
    alive: bool = True
    fitness_history: list[float] = field(default_factory=list)
    generation_born: int = 0
    cause_of_death: str | None = None

    def __post_init__(self):
        if not self.name:
            suffix = uuid.uuid4().hex[:3]
            self.name = f"{random.choice(NAMES)}-{suffix}"

    @property
    def fitness(self) -> float:
        if not self.fitness_history:
            return 0.0
        recent = self.fitness_history[-5:]
        return sum(recent) / len(recent)

    @property
    def max_age(self) -> int:
        base = 8
        return base + int(self.personality.caution * 12)

    def age_up(self) -> str | None:
        """Age the agent by one generation. Returns death cause or None."""
        self.age += 1
        if self.age >= self.max_age:
            self.alive = False
            self.cause_of_death = "old_age"
            return "old_age"
        return None

    @classmethod
    def spawn(cls, generation: int = 0) -> Agent:
        return cls(
            genome=Genome.random(generation),
            personality=Personality.random(),
            generation_born=generation,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "max_age": self.max_age,
            "alive": self.alive,
            "fitness": round(self.fitness, 3),
            "fitness_history": [round(f, 3) for f in self.fitness_history[-10:]],
            "generation_born": self.generation_born,
            "cause_of_death": self.cause_of_death,
            "genome": self.genome.to_dict(),
            "personality": self.personality.as_dict(),
            "dominant_trait": self.personality.dominant_trait,
            "hue": self.personality.hue,
        }
