# Agent-Ville

Agents that evolve through natural selection.

Not "agents that learn." Not "agents with memory." This project explores actual Darwinian evolution applied to software agent populations.

## Quick Start

```bash
python3 -m agent_ville
```

Opens at [http://localhost:8420](http://localhost:8420). Press **space** to start the simulation, **click** an agent to inspect it.

- **No dependencies** — pure Python stdlib + vanilla JS
- **Requires** Python 3.11+

## Core Idea

Traditional agent systems are designed top-down:

- Write one prompt
- Assign one toolset
- Run tasks and tune manually

Agent-Ville inverts this model. For every role and task, it spawns a small population of variants, evaluates them with a fitness function, keeps the fittest, and introduces mutations in the next generation.

The system does not ask "What prompt should we write?" It asks "Which prompt-tool-strategy genome survives?"

## The Mechanism

On first run, the system creates 5 variants for the same role.

Each variant has a different genome:

- Skill prompt variant (different generation strategy/temperature)
- Tool subset (different allowed capabilities)
- Strategy profile (conservative vs. aggressive, thorough vs. fast)

All 5 variants run the same task in isolated sandboxes.

Each output is scored by a fitness function:

```text
fitness = (
		task_completion_score * 0.4 +
		tool_efficiency * 0.2 +
		output_verification_score * 0.2 +
		execution_speed * 0.1 +
		developer_feedback * 0.1
)
```

The fittest variant survives. Its genome becomes the template for future agents in that role.

The losers are discarded.

## Why This Is Different

Most systems optimize one static agent with periodic prompt edits. Agent-Ville continuously evolves populations in production-like conditions.

Over many runs:

- Harmful mutations die out
- Neutral mutations drift
- Useful mutations spread

After enough generations, agents adapt to:

- Your codebase patterns
- Your LLM provider behavior
- Your team standards and review preferences

Two instances running in different stacks should diverge naturally:

- A Django colony evolves preferences for migrations, serializers, model signals
- A React colony evolves preferences for hooks, component boundaries, state flows

Nobody hand-codes this specialization. Selection pressure creates it.

## What This Would Look Like

### 1. Run Request

You ask a role to perform a task (for example: "Fix failing API tests").

### 2. Population Spawn

Factory creates 5 role variants from the current best genome + controlled mutations.

### 3. Isolated Execution

Each variant executes in its own capsule/subprocess with:

- Its own prompt context
- Its own tool permissions
- Its own strategy constraints

### 4. Evaluation

Registry evaluates outcomes across multiple signals:

- Did it complete the task?
- How efficiently did it use tools?
- Were claims verifiable/correct?
- How fast did it run?
- Did the developer approve the result?

### 5. Selection + Reproduction

Winner genome is persisted as new baseline for that role.
Next generation introduces small random mutations.

### 6. Long-Term Adaptation

Lineage and fitness history are tracked across runs, allowing local evolutionary pressure to shape role behavior over time.

## Minimal System Architecture

Agent-Ville assumes three key building blocks:

- Capsule isolation layer
	- Runs each variant in a sandboxed subprocess
	- Prevents cross-variant contamination
- Evolution registry
	- Stores lineage, genome snapshots, mutation metadata, and fitness trends
- Variant factory
	- Spawns candidate variants from winner genomes
	- Applies constrained mutations

Without all three, evolution collapses into ordinary prompt tuning.

## Example Genome Shape

```yaml
role: backend-fixer
prompt_profile:
	style: cautious
	constraints:
		- verify_every_claim
		- prefer_small_diffs
tool_profile:
	allowed:
		- read_file
		- apply_patch
		- run_tests
	ordering_bias:
		- inspect_before_edit
strategy_profile:
	speed_vs_thoroughness: 0.35
	risk_tolerance: 0.2
mutation_metadata:
	parent_genome_id: g142
	mutation_seed: 881204
	mutation_ops:
		- adjusted_speed_vs_thoroughness:+0.05
		- removed_tool:run_shell
```

## Example Fitness Record

```json
{
	"run_id": "r-2091",
	"role": "backend-fixer",
	"variant_id": "v-2091-3",
	"scores": {
		"task_completion_score": 0.92,
		"tool_efficiency": 0.81,
		"output_verification_score": 0.88,
		"execution_speed": 0.73,
		"developer_feedback": 1.0
	},
	"fitness": 0.87,
	"selected": true
}
```

## Mutation Strategy (Safe By Design)

Useful mutation categories:

- Prompt mutations: constraint wording, reasoning style, decomposition preference
- Tool mutations: enable/disable non-critical tools, reorder tool preference
- Strategy mutations: adjust speed-thoroughness and risk thresholds

Guardrails:

- Never mutate hard safety policies
- Never mutate sandbox boundaries
- Keep mutation deltas small for interpretability

## What Success Looks Like

The system should show measurable, role-specific adaptation over time:

- Increased mean fitness by role across generations
- Lower tool-call counts for equivalent task quality
- Higher verification accuracy on claims
- Reduced review rework for accepted outputs

The end state is not one "perfect" universal agent.
The end state is an ecosystem of locally optimized agent lineages.

## Project Positioning

Agent-Ville is an experiment in evolutionary systems for coding agents:

- Not reinforcement learning infrastructure
- Not static prompt engineering
- Not generic memory augmentation

It is selective pressure, mutation, and survival applied to practical developer workflows.