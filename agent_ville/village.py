from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .agent import Agent
from .environment import (
    BIOME_COLORS,
    CROWD_RADIUS,
    MAP_COLS,
    MAP_ROWS,
    MATING_RADIUS,
    WORLD_HEIGHT,
    WORLD_WIDTH,
    map_as_strings,
)

WITNESS_RADIUS = 2800.0     # logical units; nearby agents register a death (scaled with map)
WITNESS_DECAY = 0.85        # per-generation decay of deaths_witnessed_recent
RECENT_DEATHS_WINDOW = 20   # how many recent deaths the village remembers
DEFAULT_MEAN_DEATH_AGE = 12.0  # used before any deaths have been recorded

# Continuous selection: every generation, cull a small fraction of the eligible
# population by fitness. Without this, selection only fires when the village
# exceeds max_population, which means most generations have no fitness-based
# selection pressure at all — agents drift unchecked between crowding events.
CULL_FRACTION = 0.05            # 5% of eligible agents per generation
CULL_MIN_EVALUATIONS = 2        # grace period: agents need this many evaluations before they're judged

# Social bonuses applied on top of base fitness each generation.
# These give the spatial layer real weight: who's near you matters.
WITNESS_RADIUS_SQ = 2000.0 ** 2    # high performers radiate a small fitness boost to neighbors
WITNESS_PERF_THRESHOLD = 0.7
WITNESS_BONUS_MAX = 0.04

AID_RADIUS_SQ = 1500.0 ** 2        # elders within range mentor young
AID_YOUNG_MAX_AGE = 3
AID_ELDER_MIN_AGE = 8
AID_BONUS = 0.06
AID_ELDER_WILL_BOOST = 0.01

CONFLICT_RADIUS_SQ = 800.0 ** 2    # gives `aggression` an actual job
CONFLICT_AGGRESSION_THRESHOLD = 0.6
CONFLICT_WIN_BONUS = 0.04
CONFLICT_LOSS_PENALTY = 0.10

# Personality drift: traits move slowly in response to lived experience.
DRIFT_DEATH_WITNESS_THRESHOLD = 0.5
DRIFT_CAUTION_PER_GEN = 0.012      # witnessing death makes you more cautious
DRIFT_WILL_DECAY_PER_GEN = 0.008   # ...and chips at will_to_live (despair-leaning)
DRIFT_SUCCESS_THRESHOLD = 0.7
DRIFT_WILL_GROWTH_PER_GEN = 0.006  # sustained competence builds confidence

# Snapshot cadence. DESIGN.md suggests every ~60 generations or ~60 seconds;
# we use generations only since the sim loop is generation-paced. 50 keeps
# resume granularity tight without thrashing disk under fast play speeds.
SNAPSHOT_EVERY_N_GENS = 50

from .evolution import crossover, mutate_genome, mutate_personality, select_survivors
from .fitness import evaluate_batch
from .persistence import LineageLog, save_snapshot


@dataclass
class Event:
    generation: int
    kind: str       # birth, death, mutation, immigration
    agent_name: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "kind": self.kind,
            "agent_name": self.agent_name,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        return cls(
            generation=d.get("generation", 0),
            kind=d.get("kind", ""),
            agent_name=d.get("agent_name", ""),
            detail=d.get("detail", ""),
        )


class Village:
    def __init__(
        self,
        population_size: int = 150,
        max_population: int = 300,
        min_population: int = 60,
        lineage_log: LineageLog | None = None,
    ):
        self.target_pop = population_size
        self.max_population = max_population
        self.min_population = min_population
        self.generation = 0
        self.agents: list[Agent] = [Agent.spawn(0) for _ in range(population_size)]
        self.graveyard: list[Agent] = []
        self.events: list[Event] = []
        self.stats_history: list[dict[str, Any]] = []
        self.recent_death_ages: list[int] = []
        # None disables persistence — convenient for tests and sanity checks.
        self.lineage_log = lineage_log
        # Set by simulation.py to enable periodic snapshotting. Tests leave it None.
        from pathlib import Path
        self.snapshot_path: Path | None = None

        # Log initial births
        for a in self.agents:
            self.events.append(Event(0, "birth", a.name, "spawned in generation 0"))
            if self.lineage_log:
                self.lineage_log.log_birth(a, 0, None, None)

    @property
    def mean_death_age(self) -> float:
        if not self.recent_death_ages:
            return DEFAULT_MEAN_DEATH_AGE
        return sum(self.recent_death_ages) / len(self.recent_death_ages)

    def _log_birth(self, child: Agent, parent_a: Agent | None, parent_b: Agent | None) -> None:
        if self.lineage_log:
            self.lineage_log.log_birth(child, self.generation, parent_a, parent_b)

    def _log_death(self, agent: Agent, cause: str) -> None:
        if self.lineage_log:
            self.lineage_log.log_death(agent, self.generation, cause)

    def _record_death(self, dying: Agent, witness_pool: list[Agent]) -> None:
        """Append to recent_death_ages and propagate witness counts to nearby alive agents."""
        self.recent_death_ages.append(dying.age)
        if len(self.recent_death_ages) > RECENT_DEATHS_WINDOW:
            self.recent_death_ages = self.recent_death_ages[-RECENT_DEATHS_WINDOW:]
        r2 = WITNESS_RADIUS * WITNESS_RADIUS
        for w in witness_pool:
            if w is dying or not w.alive:
                continue
            dx = w.x - dying.x
            dy = w.y - dying.y
            if dx * dx + dy * dy <= r2:
                w.deaths_witnessed_recent += 1.0

    def motion_tick(self) -> None:
        """Advance physics for one sub-generation tick.

        Computes per-agent neighbor lists (within CROWD_RADIUS) once and passes them
        into each agent's motion step for crowd force calculation. O(n²) per tick — fine
        at populations up to ~300.
        """
        alive = [a for a in self.agents if a.alive]
        crowd_r2 = CROWD_RADIUS * CROWD_RADIUS
        mean_death_age = self.mean_death_age
        for agent in alive:
            neighbors: list[Agent] = []
            for other in alive:
                if other is agent:
                    continue
                dx = other.x - agent.x
                dy = other.y - agent.y
                if dx * dx + dy * dy <= crowd_r2:
                    neighbors.append(other)
            agent.motion_tick(
                neighbors=neighbors if neighbors else None,
                mean_death_age=mean_death_age,
            )

    def step(self) -> list[Event]:
        """Advance one generation. Returns new events."""
        self.generation += 1
        new_events: list[Event] = []

        # 0. Decay each agent's recent-death-witness counter.
        for agent in self.agents:
            if agent.alive:
                agent.deaths_witnessed_recent *= WITNESS_DECAY

        # 1. Evaluate fitness for living agents — base scores first, then social
        # bonuses (witness, aid, conflict), then commit. This is where the spatial
        # layer earns its keep: scores reflect both ability and proximity to
        # high-performers / elders / aggressors.
        alive = [a for a in self.agents if a.alive]
        base: dict[int, float] = {id(a): evaluate_batch(a, n_tasks=3) for a in alive}
        bonus: dict[int, float] = {id(a): 0.0 for a in alive}
        # Accumulators for the psyche update at end of generation.
        witness_recv: dict[int, float] = {id(a): 0.0 for a in alive}
        aid_given: dict[int, bool] = {id(a): False for a in alive}
        # Pre-cache fitness so we can compute fitness_delta later — agent.fitness
        # is property-derived and would shift mid-loop once we append the new score.
        prev_fitness: dict[int, float] = {id(a): a.fitness for a in alive}
        # Neighbor counts within crowd radius (re-used for psyche Belonging input).
        neighbor_counts: dict[int, int] = {}
        crowd_r2 = CROWD_RADIUS * CROWD_RADIUS
        for a in alive:
            c = 0
            for b in alive:
                if b is a:
                    continue
                dx = b.x - a.x
                dy = b.y - a.y
                if dx * dx + dy * dy < crowd_r2:
                    c += 1
            neighbor_counts[id(a)] = c

        # Witness: high performers radiate to nearby agents.
        for performer in alive:
            perf = base[id(performer)]
            if perf < WITNESS_PERF_THRESHOLD:
                continue
            for nearby in alive:
                if nearby is performer:
                    continue
                dx = nearby.x - performer.x
                dy = nearby.y - performer.y
                if dx * dx + dy * dy < WITNESS_RADIUS_SQ:
                    delta = WITNESS_BONUS_MAX * (perf - 0.5)
                    bonus[id(nearby)] += delta
                    witness_recv[id(nearby)] += delta

        # Aid: elders mentor young; the elder gets a will_to_live nudge in return.
        for elder in alive:
            if elder.age < AID_ELDER_MIN_AGE:
                continue
            for young in alive:
                if young is elder or young.age > AID_YOUNG_MAX_AGE:
                    continue
                dx = young.x - elder.x
                dy = young.y - elder.y
                if dx * dx + dy * dy < AID_RADIUS_SQ:
                    bonus[id(young)] += AID_BONUS
                    elder.personality.will_to_live = min(
                        1.0, elder.personality.will_to_live + AID_ELDER_WILL_BOOST
                    )
                    aid_given[id(elder)] = True
                    break  # one mentee per elder per generation

        # Conflict: aggressive agents in close range fight; outcome by aggression + noise.
        already_fought: set[int] = set()
        for a in alive:
            if id(a) in already_fought or a.personality.aggression < CONFLICT_AGGRESSION_THRESHOLD:
                continue
            for b in alive:
                if b is a or id(b) in already_fought:
                    continue
                dx = b.x - a.x
                dy = b.y - a.y
                if dx * dx + dy * dy >= CONFLICT_RADIUS_SQ:
                    continue
                a_str = a.personality.aggression + random.random() * 0.3
                b_str = b.personality.aggression + random.random() * 0.3
                winner, loser = (a, b) if a_str > b_str else (b, a)
                bonus[id(winner)] += CONFLICT_WIN_BONUS
                bonus[id(loser)] -= CONFLICT_LOSS_PENALTY
                already_fought.add(id(a))
                already_fought.add(id(b))
                new_events.append(Event(
                    self.generation, "conflict", winner.name,
                    f"beat {loser.name} in a clash",
                ))
                break

        # Commit final scores.
        for agent in alive:
            final = max(0.0, min(1.0, base[id(agent)] + bonus[id(agent)]))
            agent.fitness_history.append(final)

        # 1b. Personality drift — lived experience nudges traits.
        for agent in alive:
            if agent.deaths_witnessed_recent > DRIFT_DEATH_WITNESS_THRESHOLD:
                agent.personality.caution = min(
                    1.0, agent.personality.caution + DRIFT_CAUTION_PER_GEN
                )
                agent.personality.will_to_live = max(
                    0.0, agent.personality.will_to_live - DRIFT_WILL_DECAY_PER_GEN
                )
            if agent.fitness > DRIFT_SUCCESS_THRESHOLD:
                agent.personality.will_to_live = min(
                    1.0, agent.personality.will_to_live + DRIFT_WILL_GROWTH_PER_GEN
                )

        # 1c. Psyche update — needs respond to the signals the social phase produced.
        # Refresh dominant pursuit afterward so the next generation's motion ticks
        # read the current need-driven goal.
        for agent in alive:
            agent.psyche.update(
                fitness=agent.fitness,
                fitness_delta=agent.fitness - prev_fitness[id(agent)],
                neighbor_count=neighbor_counts[id(agent)],
                deaths_witnessed_recent=agent.deaths_witnessed_recent,
                witness_bonus_received=witness_recv[id(agent)],
                aid_given=aid_given[id(agent)],
            )
            agent.current_pursuit = agent.psyche.dominant_pursuit(agent.personality)

        # 1d. Despair death — sustained low flourishing kills the agent.
        # Separate from old_age and selection; it's a psyche-mediated mortality pathway.
        for agent in list(alive):
            if not agent.alive:
                continue
            if agent.psyche.in_despair():
                agent.alive = False
                agent.cause_of_death = "despair"
                self._record_death(agent, witness_pool=alive)
                self._log_death(agent, "despair")
                new_events.append(Event(
                    self.generation, "death", agent.name,
                    f"died of despair (flourishing {agent.psyche.flourishing(agent.personality):.2f})",
                ))

        # 2. Age all living agents
        for agent in alive:
            cause = agent.age_up()
            if cause:
                self._record_death(agent, witness_pool=alive)
                self._log_death(agent, cause)
                new_events.append(Event(
                    self.generation, "death", agent.name,
                    f"died of {cause} at age {agent.age}",
                ))

        # 3. Continuous selection — cull the weakest fraction every generation.
        # Newborns with too few evaluations are protected from being judged.
        alive = [a for a in self.agents if a.alive]
        eligible = [a for a in alive if len(a.fitness_history) >= CULL_MIN_EVALUATIONS]
        n_cull = int(len(eligible) * CULL_FRACTION)
        if n_cull > 0:
            eligible.sort(key=lambda a: a.fitness)
            for agent in eligible[:n_cull]:
                agent.alive = False
                agent.cause_of_death = "selection"
                self._record_death(agent, witness_pool=alive)
                self._log_death(agent, "selection")
                new_events.append(Event(
                    self.generation, "death", agent.name,
                    f"culled (fitness {agent.fitness:.2f})",
                ))

        # 4. Overcrowding backstop — hard cap at max_population.
        alive = [a for a in self.agents if a.alive]
        if len(alive) > self.max_population:
            survivors = select_survivors(alive, self.target_pop)
            killed = set(id(a) for a in alive) - set(id(a) for a in survivors)
            for agent in alive:
                if id(agent) in killed:
                    agent.alive = False
                    agent.cause_of_death = "selection"
                    self._record_death(agent, witness_pool=alive)
                    self._log_death(agent, "selection")
                    new_events.append(Event(
                        self.generation, "death", agent.name,
                        f"eliminated by selection (fitness {agent.fitness:.2f})",
                    ))

        # 5. Reproduce — proximity-required mating.
        # Top-fitness agents seek a compatible partner within MATING_RADIUS.
        # Agents with no nearby partner do not reproduce this generation — this is
        # where spatial isolation drives lineage divergence.
        alive = [a for a in self.agents if a.alive]
        births_needed = max(0, self.target_pop - len(alive))

        if len(alive) >= 2 and births_needed > 0:
            ranked = sorted(alive, key=lambda a: a.fitness, reverse=True)
            top = ranked[: max(2, len(ranked) // 2)]
            mating_r2 = MATING_RADIUS * MATING_RADIUS
            random.shuffle(top)  # don't always favor the same parent ordering
            births = 0
            already_mated: set[int] = set()
            for parent_a in top:
                if births >= births_needed:
                    break
                if id(parent_a) in already_mated:
                    continue
                # Find best nearby partner that hasn't mated this generation.
                best_partner = None
                best_partner_fitness = -1.0
                for parent_b in top:
                    if parent_b is parent_a or id(parent_b) in already_mated:
                        continue
                    dx = parent_b.x - parent_a.x
                    dy = parent_b.y - parent_a.y
                    if dx * dx + dy * dy <= mating_r2:
                        if parent_b.fitness > best_partner_fitness:
                            best_partner = parent_b
                            best_partner_fitness = parent_b.fitness
                if best_partner is None:
                    continue
                already_mated.add(id(parent_a))
                already_mated.add(id(best_partner))
                child = crossover(parent_a, best_partner, self.generation)
                self.agents.append(child)
                self._log_birth(child, parent_a, best_partner)
                new_events.append(Event(
                    self.generation, "birth", child.name,
                    f"born from {parent_a.name} x {best_partner.name}",
                ))
                births += 1
            # Immigration backstop: if proximity mating couldn't fill the quota
            # (sparse population, isolated agents), make up some of the shortfall.
            shortfall = births_needed - births
            if shortfall > 0:
                # Cover up to half the shortfall via immigration so populations
                # don't crash, but mating still has to do the bulk of the work.
                fill = max(1, shortfall // 2)
                for _ in range(fill):
                    child = Agent.spawn(self.generation)
                    self.agents.append(child)
                    self._log_birth(child, None, None)
                    new_events.append(Event(
                        self.generation, "immigration", child.name,
                        "arrived (mating shortfall)",
                    ))
        elif births_needed > 0:
            # Not enough agents — spontaneous immigrant
            for _ in range(births_needed):
                child = Agent.spawn(self.generation)
                self.agents.append(child)
                self._log_birth(child, None, None)
                new_events.append(Event(
                    self.generation, "immigration", child.name,
                    "arrived as immigrant",
                ))

        # 6. Occasional random immigrant (genetic diversity)
        alive_count = sum(1 for a in self.agents if a.alive)
        if random.random() < 0.1 and alive_count < self.max_population:
            immigrant = Agent.spawn(self.generation)
            self.agents.append(immigrant)
            self._log_birth(immigrant, None, None)
            new_events.append(Event(
                self.generation, "immigration", immigrant.name,
                "arrived as immigrant",
            ))

        # 7. Move dead to graveyard
        newly_dead = [a for a in self.agents if not a.alive and a not in self.graveyard]
        self.graveyard.extend(newly_dead)

        # 8. Record stats
        alive = [a for a in self.agents if a.alive]
        if alive:
            fitnesses = [a.fitness for a in alive]
            self.stats_history.append({
                "generation": self.generation,
                "population": len(alive),
                "avg_fitness": round(sum(fitnesses) / len(fitnesses), 3),
                "max_fitness": round(max(fitnesses), 3),
                "min_fitness": round(min(fitnesses), 3),
                "total_deaths": len(self.graveyard),
            })

        self.events.extend(new_events)

        # 9. Periodic snapshot for resume.
        if self.snapshot_path is not None and self.generation % SNAPSHOT_EVERY_N_GENS == 0:
            save_snapshot(self, self.snapshot_path)

        return new_events

    def to_snapshot(self) -> dict[str, Any]:
        """Full state, structured for json.dumps + from_snapshot round-trip."""
        return {
            "generation": self.generation,
            "target_pop": self.target_pop,
            "max_population": self.max_population,
            "min_population": self.min_population,
            "agents": [a.to_snapshot() for a in self.agents if a.alive],
            # Retention: cap graveyard at 10k to bound snapshot growth (per DESIGN.md).
            "graveyard": [a.to_snapshot() for a in self.graveyard[-10_000:]],
            "events": [e.to_dict() for e in self.events[-10_000:]],
            "stats_history": self.stats_history[-1_000:],
            "recent_death_ages": list(self.recent_death_ages),
        }

    @classmethod
    def from_snapshot(
        cls,
        d: dict[str, Any],
        lineage_log: LineageLog | None = None,
    ) -> Village:
        v = cls.__new__(cls)
        v.target_pop = d.get("target_pop", 150)
        v.max_population = d.get("max_population", 300)
        v.min_population = d.get("min_population", 60)
        v.generation = d.get("generation", 0)
        v.agents = [Agent.from_snapshot(x) for x in d.get("agents", [])]
        v.graveyard = [Agent.from_snapshot(x) for x in d.get("graveyard", [])]
        v.events = [Event.from_dict(x) for x in d.get("events", [])]
        v.stats_history = list(d.get("stats_history", []))
        v.recent_death_ages = list(d.get("recent_death_ages", []))
        v.lineage_log = lineage_log
        from pathlib import Path
        v.snapshot_path: Path | None = None
        return v

    def get_state(self) -> dict[str, Any]:
        alive = [a for a in self.agents if a.alive]
        mean_age = self.mean_death_age
        return {
            "generation": self.generation,
            "world": {
                "width": WORLD_WIDTH,
                "height": WORLD_HEIGHT,
                "map": {
                    "cols": MAP_COLS,
                    "rows": MAP_ROWS,
                    "tiles": map_as_strings(),
                    "colors": {b.value: c for b, c in BIOME_COLORS.items()},
                },
            },
            "mortality": {
                "mean_death_age": round(mean_age, 2),
                "recent_death_ages": list(self.recent_death_ages),
            },
            "agents": [
                {**a.to_dict(), "mortality_pressure": round(a.mortality_pressure(mean_age), 3)}
                for a in alive
            ],
            "graveyard_size": len(self.graveyard),
            "recent_dead": [a.to_dict() for a in self.graveyard[-5:]],
            "events": [e.to_dict() for e in self.events[-30:]],
            "stats_history": self.stats_history[-50:],
        }
