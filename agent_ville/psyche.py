"""Sixfold psyche — six simultaneously-active needs that update each generation.

This is the minimum viable version of DESIGN.md's Psyche layer. It introduces:

- 6 needs (Body, Safety, Belonging, Esteem, Becoming, Beyond), each in [0, 1].
- Per-generation depletion + signal-driven replenishment.
- A dominant pursuit (the most-urgent need this tick) that biases motion.
- A despair-death pathway when sustained flourishing falls below a threshold.

What this does NOT yet do, on purpose:

- Multi-architecture diversity (no ERG or MaslowSim variants).
- Regression / expansion across architectures.
- Biography / event log / life-phase aggregates.
- Mate signatures (mating still uses fitness rank).

Each absent piece is documented in DESIGN.md as a separate layer; the value
of this slice is that the agent's *visible* behavior is now driven by needs,
not by trait optimization alone — and that's where the simulation starts to
behave like something more than a hill-climber.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .personality import Personality

NEEDS = ("body", "safety", "belonging", "esteem", "becoming", "beyond")

# Per-need depletion per generation. Body and Belonging deplete fastest — they
# correspond to the most physical/social drives. Beyond is slowest — a higher
# need that doesn't urgently demand attention from moment to moment.
_DEPLETION = {
    "body":      0.05,
    "safety":    0.04,
    "belonging": 0.05,
    "esteem":    0.03,
    "becoming":  0.02,
    "beyond":    0.01,
}

# Despair: sustained low flourishing eventually kills the agent.
DESPAIR_THRESHOLD = 0.30
DESPAIR_DEATH_STREAK = 8


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class Sixfold:
    body: float = 0.7
    safety: float = 0.6
    belonging: float = 0.5
    esteem: float = 0.5
    becoming: float = 0.5
    beyond: float = 0.3
    # Consecutive generations of flourishing below DESPAIR_THRESHOLD.
    despair_streak: int = 0

    def update(
        self,
        *,
        fitness: float,
        fitness_delta: float,
        neighbor_count: int,
        deaths_witnessed_recent: float,
        witness_bonus_received: float,
        aid_given: bool,
    ) -> None:
        """Tick all needs once. Replenishment signals are drawn from existing
        per-generation observations the simulation already computes."""
        # Body: fed by competence (earn your keep). High fitness → satiety.
        self.body = _clip(self.body - _DEPLETION["body"] + fitness * 0.08)

        # Safety: eroded by witnessed deaths; passively recovers in quiet times.
        safety_input = (1.0 - min(1.0, deaths_witnessed_recent / 4.0)) * 0.05
        self.safety = _clip(self.safety - _DEPLETION["safety"] + safety_input)

        # Belonging: proximity to others.
        self.belonging = _clip(
            self.belonging - _DEPLETION["belonging"] + min(1.0, neighbor_count / 8.0) * 0.06
        )

        # Esteem: being witnessed performing well (bonus received in the witness phase).
        self.esteem = _clip(self.esteem - _DEPLETION["esteem"] + witness_bonus_received * 3.0)

        # Becoming: growth — only positive fitness deltas count.
        self.becoming = _clip(self.becoming - _DEPLETION["becoming"] + max(0.0, fitness_delta) * 0.5)

        # Beyond: only fed by giving aid (Sixfold's higher-order need).
        self.beyond = _clip(self.beyond - _DEPLETION["beyond"] + (0.08 if aid_given else 0.0))

        # Despair tracking: streak grows below threshold, decays above.
        if self.flourishing() < DESPAIR_THRESHOLD:
            self.despair_streak += 1
        else:
            self.despair_streak = max(0, self.despair_streak - 1)

    def _weights(self, p: Personality) -> dict[str, float]:
        """Personality-modulated need weights. Sociable agents weight Belonging
        more; cautious weight Safety; curious weight Becoming; etc."""
        return {
            "body":      1.0,
            "safety":    0.7 + p.caution * 0.6,
            "belonging": 0.5 + p.sociability * 0.8,
            "esteem":    0.5 + p.aggression * 0.4 + p.creativity * 0.2,
            "becoming":  0.5 + p.curiosity * 0.8,
            "beyond":    0.3 + p.will_to_live * 0.4,
        }

    def flourishing(self, personality: Personality | None = None) -> float:
        """Weighted mean of need satisfactions. Selection-grade scalar in [0, 1]."""
        if personality is None:
            return sum(getattr(self, n) for n in NEEDS) / len(NEEDS)
        w = self._weights(personality)
        return sum(getattr(self, n) * w[n] for n in NEEDS) / sum(w.values())

    def dominant_pursuit(self, personality: Personality) -> str:
        """The need with the highest urgency = (1 - satisfaction) * weight."""
        w = self._weights(personality)
        return max(NEEDS, key=lambda n: (1.0 - getattr(self, n)) * w[n])

    def in_despair(self) -> bool:
        return self.despair_streak >= DESPAIR_DEATH_STREAK

    def to_snapshot(self) -> dict[str, Any]:
        return {n: round(getattr(self, n), 3) for n in NEEDS} | {
            "despair_streak": self.despair_streak,
        }

    @classmethod
    def from_snapshot(cls, d: dict[str, Any]) -> Sixfold:
        return cls(
            body=d.get("body", 0.5),
            safety=d.get("safety", 0.5),
            belonging=d.get("belonging", 0.5),
            esteem=d.get("esteem", 0.5),
            becoming=d.get("becoming", 0.5),
            beyond=d.get("beyond", 0.3),
            despair_streak=d.get("despair_streak", 0),
        )
