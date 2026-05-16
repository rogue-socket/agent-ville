from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from .environment import (
    BIOME_RULES,
    CROWD_FORCE_SCALE,
    FIT_SEEK_FORCE_SCALE,
    MAP_COLS,
    MAP_ROWS,
    MOTION_BOUNDARY_MARGIN,
    MOTION_DAMPING,
    MOTION_IMPULSE_BASE,
    MOTION_MAX_SPEED,
    TILE_HEIGHT,
    TILE_WIDTH,
    WORLD_HEIGHT,
    WORLD_WIDTH,
    agent_biome_fit,
    biome_at,
)
from .environment import MAP as _MAP
from .genome import Genome
from .personality import Personality
from .psyche import Sixfold

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

    # Spatial state (logical units; see environment.WORLD_WIDTH/HEIGHT)
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0

    # Decaying count of nearby deaths witnessed in recent generations.
    # Drives mortality awareness alongside the village-wide mean_death_age.
    deaths_witnessed_recent: float = 0.0

    # Six-need psyche layer. Driven by Village.step()'s per-gen update call.
    psyche: Sixfold = field(default_factory=Sixfold)
    # Refreshed once per generation after psyche.update(). Read every motion tick
    # to bias the existing motion forces — avoids re-deriving dominance 30×/gen.
    current_pursuit: str = "body"

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
        # Lifespan is fitness-driven: earn your keep, live longer. Range [8, 20].
        # New agents start at the floor and extend it as their fitness history fills in.
        # A fitness collapse can shorten max_age below current age — that's the point:
        # losing competence means losing standing.
        base = 8
        return base + int(self.fitness * 12)

    def age_up(self) -> str | None:
        """Age the agent by one generation. Returns death cause or None."""
        self.age += 1
        if self.age >= self.max_age:
            self.alive = False
            self.cause_of_death = "old_age"
            return "old_age"
        return None

    def mortality_pressure(self, mean_death_age: float) -> float:
        """How strongly this agent feels its mortality right now. 0..~1.5.

        Combines age vs. local mortality norm and recent witnessed deaths,
        gated by personal will_to_live. An agent with will_to_live=0 has zero
        pressure regardless of conditions; an agent with high will_to_live
        feels pressure earlier and more strongly.
        """
        if mean_death_age <= 0:
            return 0.0
        age_signal = max(0.0, (self.age / mean_death_age) - 0.5)
        witness_signal = self.deaths_witnessed_recent * 0.08
        return (age_signal + witness_signal) * self.personality.will_to_live

    def motion_tick(
        self,
        neighbors: list[Agent] | None = None,
        mean_death_age: float = 12.0,
    ) -> None:
        """One sub-generation physics step.

        Forces (all summed):
          1. Brownian impulse, magnitude scaled by curiosity and biome speed.
          2. Biome-fit-seek: gradient ascent toward the most-fitting neighbor tile.
             Under mortality pressure, fit is augmented by a safety bonus that biases
             agents toward low-risk biomes (Plains, Forest, Coast).
          3. Crowd force: sociable agents pulled to neighbor centroid; antisocial pushed away.
          4. Mortality response: agents with high mortality_pressure slow down.
        Then damping, velocity clamp, integrate, reflective boundary.
        """
        current_biome = biome_at(self.x, self.y)
        biome_mult = BIOME_RULES[current_biome].speed_mult
        mort = self.mortality_pressure(mean_death_age)

        # Dominant pursuit biases existing forces — no new force categories, just
        # weight shifts. Becoming → roam more; Body → seek best biome harder;
        # Safety → lean harder on the mortality bias; Belonging → cling to crowds.
        pursuit = self.current_pursuit
        impulse_mult = 1.5 if pursuit == "becoming" else 1.0
        seek_mult = 1.5 if pursuit == "body" else 1.0
        crowd_mult = 1.7 if pursuit == "belonging" else 1.0
        if pursuit == "safety":
            mort = min(1.5, mort * 1.5)

        # 1. Brownian impulse, modulated by biome and mortality (dying agents move less)
        impulse = MOTION_IMPULSE_BASE * (0.5 + self.personality.curiosity) * biome_mult * impulse_mult
        impulse *= max(0.2, 1.0 - mort * 0.5)
        self.vx += (random.random() - 0.5) * impulse
        self.vy += (random.random() - 0.5) * impulse

        # 2. Biome-fit-seek with mortality-driven safety bias.
        col = int(max(0, min(MAP_COLS - 1, self.x // TILE_WIDTH)))
        row = int(max(0, min(MAP_ROWS - 1, self.y // TILE_HEIGHT)))

        def tile_score(biome) -> float:
            base = agent_biome_fit(self.genome.speed_vs_thoroughness, self.genome.allowed_tools, biome)
            # Safety bonus: low-risk biomes favored under mortality pressure.
            safety = (1.0 - BIOME_RULES[biome].risk_pref) * mort * 0.6
            return base + safety

        my_score = tile_score(_MAP[row][col])
        best_score = my_score
        best_dx = 0.0
        best_dy = 0.0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if 0 <= nr < MAP_ROWS and 0 <= nc < MAP_COLS:
                    s = tile_score(_MAP[nr][nc])
                    if s > best_score + 0.02:
                        best_score = s
                        best_dx = dc
                        best_dy = dr
        if best_dx != 0 or best_dy != 0:
            mag = math.hypot(best_dx, best_dy)
            # Dying agents seek safety harder than curious agents wander.
            seek_scale = FIT_SEEK_FORCE_SCALE * (1.0 - self.personality.curiosity * 0.5 + mort * 0.5) * seek_mult
            self.vx += (best_dx / mag) * seek_scale
            self.vy += (best_dy / mag) * seek_scale

        # 3. Crowd force — toward (sociable) or away from (antisocial) neighbor centroid.
        if neighbors:
            cx = sum(n.x for n in neighbors) / len(neighbors)
            cy = sum(n.y for n in neighbors) / len(neighbors)
            dx = cx - self.x
            dy = cy - self.y
            dist = math.hypot(dx, dy)
            if dist > 0.01:
                pull = (self.personality.sociability - 0.5) * 2.0  # in [-1, 1]
                self.vx += (dx / dist) * CROWD_FORCE_SCALE * pull * crowd_mult
                self.vy += (dy / dist) * CROWD_FORCE_SCALE * pull * crowd_mult

        # Damping (cautious agents get more; dying agents get more)
        damping = MOTION_DAMPING * (1.0 - self.personality.caution * 0.04 - mort * 0.05)
        damping = max(0.6, damping)
        self.vx *= damping
        self.vy *= damping

        # Velocity clamp
        speed = math.hypot(self.vx, self.vy)
        if speed > MOTION_MAX_SPEED:
            scale = MOTION_MAX_SPEED / speed
            self.vx *= scale
            self.vy *= scale

        # Integrate
        self.x += self.vx
        self.y += self.vy

        # Reflective boundary
        m = MOTION_BOUNDARY_MARGIN
        if self.x < m:
            self.x = m
            self.vx = -self.vx
        elif self.x > WORLD_WIDTH - m:
            self.x = WORLD_WIDTH - m
            self.vx = -self.vx
        if self.y < m:
            self.y = m
            self.vy = -self.vy
        elif self.y > WORLD_HEIGHT - m:
            self.y = WORLD_HEIGHT - m
            self.vy = -self.vy

    @classmethod
    def spawn(cls, generation: int = 0) -> Agent:
        return cls(
            genome=Genome.random(generation),
            personality=Personality.random(),
            generation_born=generation,
            x=random.uniform(0, WORLD_WIDTH),
            y=random.uniform(0, WORLD_HEIGHT),
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
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "biome": biome_at(self.x, self.y).value,
            "deaths_witnessed_recent": round(self.deaths_witnessed_recent, 3),
            "psyche": self.psyche.to_snapshot(),
            "flourishing": round(self.psyche.flourishing(self.personality), 3),
            "current_pursuit": self.current_pursuit,
        }

    def to_snapshot(self) -> dict[str, Any]:
        """Lossless serialization for resume. Distinct from to_dict (which is
        API-shaped and lossy on history + missing velocity)."""
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "alive": self.alive,
            # Keep only what the rolling-5 fitness window can use; older values are dead weight.
            "fitness_history": list(self.fitness_history[-5:]),
            "generation_born": self.generation_born,
            "cause_of_death": self.cause_of_death,
            "x": self.x, "y": self.y, "vx": self.vx, "vy": self.vy,
            "deaths_witnessed_recent": self.deaths_witnessed_recent,
            "genome": self.genome.to_dict(),
            "personality": self.personality.as_dict(),
            "psyche": self.psyche.to_snapshot(),
            "current_pursuit": self.current_pursuit,
        }

    @classmethod
    def from_snapshot(cls, d: dict[str, Any]) -> Agent:
        return cls(
            id=d["id"],
            name=d["name"],
            genome=Genome.from_dict(d["genome"]),
            personality=Personality.from_dict(d["personality"]),
            age=d.get("age", 0),
            alive=d.get("alive", True),
            fitness_history=list(d.get("fitness_history", [])),
            generation_born=d.get("generation_born", 0),
            cause_of_death=d.get("cause_of_death"),
            x=d.get("x", 0.0), y=d.get("y", 0.0),
            vx=d.get("vx", 0.0), vy=d.get("vy", 0.0),
            deaths_witnessed_recent=d.get("deaths_witnessed_recent", 0.0),
            psyche=Sixfold.from_snapshot(d["psyche"]) if "psyche" in d else Sixfold(),
            current_pursuit=d.get("current_pursuit", "body"),
        )
