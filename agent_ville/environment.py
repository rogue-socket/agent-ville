"""World dimensions, biome map, and motion physics constants.

Logical coordinate space; the frontend scales these to canvas pixels.
Map is procedurally generated with a fixed seed so the same world appears every run.
"""
from __future__ import annotations

import random as _random
from dataclasses import dataclass
from enum import Enum

from .genome import ALL_TOOLS

# World dimensions — 40000×24000 logical units.
# At default pop=150 this gives ~6.4M area units per agent (close to Earth-like density).
WORLD_WIDTH = 40000.0
WORLD_HEIGHT = 24000.0

# Map resolution — 50×30 tiles. Each tile is 800×800 logical units.
# Tile count is unchanged from the prototype so map structure renders identically on canvas.
MAP_COLS = 50
MAP_ROWS = 30
TILE_WIDTH = WORLD_WIDTH / MAP_COLS
TILE_HEIGHT = WORLD_HEIGHT / MAP_ROWS
MAP_SEED = 42

# Motion physics — all scaled by 80× (linear scale factor) from the prototype
# so behavior in tiles-per-generation is unchanged.
MOTION_DAMPING = 0.92
MOTION_IMPULSE_BASE = 17.6
MOTION_MAX_SPEED = 320.0
MOTION_BOUNDARY_MARGIN = 160.0

# Interaction radii (logical units)
MATING_RADIUS = 3200.0
CROWD_RADIUS = 2800.0

# Force scales — small per-tick contributions; integrated over many ticks
CROWD_FORCE_SCALE = 4.0
FIT_SEEK_FORCE_SCALE = 6.4


class Biome(Enum):
    FOREST = "forest"
    DESERT = "desert"
    MARSH = "marsh"
    COAST = "coast"
    TUNDRA = "tundra"
    PLAINS = "plains"


@dataclass(frozen=True)
class BiomeRules:
    speed_pref: float       # task ideal_speed centered here
    thorough_pref: float    # task ideal_thoroughness centered here
    risk_pref: float        # task risk_level centered here
    tool_pool: tuple[str, ...]
    speed_mult: float = 1.0  # multiplier applied to motion impulse in this biome


BIOME_RULES: dict[Biome, BiomeRules] = {
    Biome.FOREST:  BiomeRules(0.2, 0.8, 0.2, ("read", "analyze"),       speed_mult=0.9),
    Biome.DESERT:  BiomeRules(0.8, 0.2, 0.8, ("execute", "search"),     speed_mult=1.2),
    Biome.MARSH:   BiomeRules(0.5, 0.5, 0.7, ("write", "communicate"),  speed_mult=0.55),
    Biome.COAST:   BiomeRules(0.5, 0.5, 0.3, ("communicate", "search"), speed_mult=1.0),
    Biome.TUNDRA:  BiomeRules(0.3, 0.7, 0.5, ("search", "analyze"),     speed_mult=0.7),
    Biome.PLAINS:  BiomeRules(0.5, 0.5, 0.5, tuple(ALL_TOOLS),          speed_mult=1.1),
}

BIOME_COLORS: dict[Biome, str] = {
    Biome.FOREST:  "#2d3a2e",
    Biome.DESERT:  "#5a4e2e",
    Biome.MARSH:   "#3e2e4a",
    Biome.COAST:   "#2e4a5a",
    Biome.TUNDRA:  "#4a5260",
    Biome.PLAINS:  "#4a3e2e",
}


def _generate_map(seed: int) -> list[list[Biome]]:
    """Seeded Voronoi-style map: pick region centers, each tile gets nearest center's biome.

    Guarantees all 6 biomes appear (one center per biome, then random extras).
    """
    rng = _random.Random(seed)
    n_extra_centers = 12  # plus the 6 guaranteed → 18 regions
    biome_list = list(Biome)

    # One guaranteed center per biome, spread roughly across the map.
    centers: list[tuple[float, float, Biome]] = []
    shuffled = list(biome_list)
    rng.shuffle(shuffled)
    for biome in shuffled:
        cx = rng.uniform(0, MAP_COLS)
        cy = rng.uniform(0, MAP_ROWS)
        centers.append((cx, cy, biome))

    # Extra centers — repeat biomes to grow some regions larger.
    for _ in range(n_extra_centers):
        biome = rng.choice(biome_list)
        cx = rng.uniform(0, MAP_COLS)
        cy = rng.uniform(0, MAP_ROWS)
        centers.append((cx, cy, biome))

    grid: list[list[Biome]] = []
    for r in range(MAP_ROWS):
        row: list[Biome] = []
        for c in range(MAP_COLS):
            tx = c + 0.5
            ty = r + 0.5
            best_dist = float("inf")
            best_biome = Biome.PLAINS
            for cx, cy, b in centers:
                dx = cx - tx
                dy = cy - ty
                d = dx * dx + dy * dy
                if d < best_dist:
                    best_dist = d
                    best_biome = b
            row.append(best_biome)
        grid.append(row)

    # Light edge irregularity: ~8% of tiles adopt a random neighbor's biome.
    noisy = [row[:] for row in grid]
    for r in range(MAP_ROWS):
        for c in range(MAP_COLS):
            if rng.random() < 0.08:
                neighbors = []
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < MAP_ROWS and 0 <= nc < MAP_COLS:
                        neighbors.append(grid[nr][nc])
                if neighbors:
                    noisy[r][c] = rng.choice(neighbors)
    return noisy


MAP: list[list[Biome]] = _generate_map(MAP_SEED)


def biome_at(x: float, y: float) -> Biome:
    col = int(max(0, min(MAP_COLS - 1, x // TILE_WIDTH)))
    row = int(max(0, min(MAP_ROWS - 1, y // TILE_HEIGHT)))
    return MAP[row][col]


def map_as_strings() -> list[list[str]]:
    """Serialize MAP as biome names for the API."""
    return [[b.value for b in row] for row in MAP]


def agent_biome_fit(speed_vs_thoroughness: float, allowed_tools: list[str], biome: Biome) -> float:
    """Cheap deterministic estimate of how well an agent suits a biome. 0..1.

    Used by biome-fit-seek motion force — does not consume RNG.
    """
    rules = BIOME_RULES[biome]
    speed_fit = 1.0 - abs(speed_vs_thoroughness - rules.speed_pref)
    thorough_fit = 1.0 - abs((1.0 - speed_vs_thoroughness) - rules.thorough_pref)
    needed = set(rules.tool_pool)
    has = set(allowed_tools)
    tool_coverage = len(has & needed) / max(1, len(needed))
    return 0.4 * speed_fit + 0.3 * thorough_fit + 0.3 * tool_coverage
