from __future__ import annotations

import random
from dataclasses import dataclass


TRAIT_NAMES = ["curiosity", "aggression", "caution", "sociability", "creativity"]

# Hue mapping for visualization (HSL)
TRAIT_HUES = {
    "curiosity": 45,    # gold
    "aggression": 0,    # red
    "caution": 210,     # blue
    "sociability": 120, # green
    "creativity": 280,  # purple
}


@dataclass
class Personality:
    curiosity: float      # exploration vs exploitation
    aggression: float     # competitive vs cooperative
    caution: float        # risk-averse vs risk-seeking
    sociability: float    # collaborative vs solitary
    creativity: float     # novel vs conventional

    @classmethod
    def random(cls) -> Personality:
        return cls(
            curiosity=random.random(),
            aggression=random.random(),
            caution=random.random(),
            sociability=random.random(),
            creativity=random.random(),
        )

    @property
    def dominant_trait(self) -> str:
        traits = self.as_dict()
        return max(traits, key=traits.get)

    @property
    def hue(self) -> int:
        return TRAIT_HUES[self.dominant_trait]

    def as_dict(self) -> dict[str, float]:
        return {
            "curiosity": round(self.curiosity, 3),
            "aggression": round(self.aggression, 3),
            "caution": round(self.caution, 3),
            "sociability": round(self.sociability, 3),
            "creativity": round(self.creativity, 3),
        }
