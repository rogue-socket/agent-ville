"""Append-only lineage TSV.

The simulation's in-memory `graveyard` is bounded; old deaths fall off as a
run continues. Stats history is similarly capped. Without an external record
the parent->child graph evaporates as the run progresses, which makes the
long-run dynamics this simulation is built to study unobservable.

This module writes one row per birth and one row per death to a flat TSV.
Append-only: no in-place edits, no reads, no recovery logic. Designed for
post-hoc analysis (load with pandas/polars/awk), not for resume. Multiple
sessions coexist in the same file via a `session_id` column = the village's
start timestamp.

Threading: writes happen from `Village.step()` which is already serialized
behind `SimulationState._lock`. A local lock is included anyway so direct
test usage doesn't surprise the caller.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .agent import Agent
from .environment import biome_at

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_LINEAGE_PATH = DATA_DIR / "lineage.tsv"
DEFAULT_SNAPSHOT_PATH = DATA_DIR / "snapshot.json"
SNAPSHOT_SCHEMA_VERSION = 1

COLUMNS = (
    "session_id", "event", "gen", "agent_id", "name",
    "parent_a", "parent_b", "genome_id",
    "cause", "age", "fitness", "biome", "x", "y",
    # Genome snapshot — enables trait-drift analysis along the lineage tree.
    "g_speed", "g_risk", "g_tools",
    # Personality snapshot — same.
    "p_curiosity", "p_aggression", "p_caution",
    "p_sociability", "p_creativity", "p_will_to_live",
)


def _trait_fields(agent: Agent) -> dict[str, Any]:
    g, p = agent.genome, agent.personality
    return {
        "g_speed": round(g.speed_vs_thoroughness, 3),
        "g_risk": round(g.risk_tolerance, 3),
        # allowed_tools is multi-value; sort + comma-join keeps it parseable inside one TSV cell.
        "g_tools": ",".join(sorted(g.allowed_tools)),
        "p_curiosity": round(p.curiosity, 3),
        "p_aggression": round(p.aggression, 3),
        "p_caution": round(p.caution, 3),
        "p_sociability": round(p.sociability, 3),
        "p_creativity": round(p.creativity, 3),
        "p_will_to_live": round(p.will_to_live, 3),
    }


class LineageLog:
    def __init__(
        self,
        path: Path = DEFAULT_LINEAGE_PATH,
        session_id: int | None = None,
    ) -> None:
        self.path = path
        # Resume from a snapshot reuses the prior session_id so the lineage
        # rows stay linkable across restarts. Fresh runs get a new timestamp.
        self.session_id = session_id if session_id is not None else int(time.time())
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write header on first creation only — append mode never re-writes it.
        if not self.path.exists():
            self.path.write_text("\t".join(COLUMNS) + "\n")

    def _write(self, row: dict[str, Any]) -> None:
        line = "\t".join(str(row.get(col, "")) for col in COLUMNS) + "\n"
        with self._lock, self.path.open("a") as f:
            f.write(line)

    def log_birth(
        self,
        child: Agent,
        gen: int,
        parent_a: Agent | None,
        parent_b: Agent | None,
    ) -> None:
        self._write({
            "session_id": self.session_id,
            "event": "birth",
            "gen": gen,
            "agent_id": child.id,
            "name": child.name,
            "parent_a": parent_a.id if parent_a else "",
            "parent_b": parent_b.id if parent_b else "",
            "genome_id": child.genome.id,
            "biome": biome_at(child.x, child.y).value,
            "x": round(child.x, 1),
            "y": round(child.y, 1),
            **_trait_fields(child),
        })

    def log_death(self, agent: Agent, gen: int, cause: str) -> None:
        self._write({
            "session_id": self.session_id,
            "event": "death",
            "gen": gen,
            "agent_id": agent.id,
            "name": agent.name,
            "genome_id": agent.genome.id,
            "cause": cause,
            "age": agent.age,
            "fitness": round(agent.fitness, 3),
            "biome": biome_at(agent.x, agent.y).value,
            "x": round(agent.x, 1),
            "y": round(agent.y, 1),
            **_trait_fields(agent),
        })


def save_snapshot(village: Any, path: Path = DEFAULT_SNAPSHOT_PATH) -> None:
    """Atomically write a full village snapshot to disk.

    The village owns the serialization shape via `to_snapshot()`; this helper
    just adds the schema version, lineage session_id, and the tmp+rename dance.
    """
    payload = village.to_snapshot()
    payload["version"] = SNAPSHOT_SCHEMA_VERSION
    if village.lineage_log is not None:
        payload["lineage_session_id"] = village.lineage_log.session_id
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, path)


def load_snapshot(path: Path = DEFAULT_SNAPSHOT_PATH) -> dict[str, Any] | None:
    """Return the snapshot dict, or None if no file exists / can't be parsed."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
