# Subagent registry

The multi-agent workflow for this repo. **Main** (the chat session you're reading) is the
**orchestrator** — it grills requirements, plans, dispatches, and owns integration. It does NOT
implement or self-verify. Dispatch work to the agents below via the `Agent` tool
(`subagent_type: <name>`). This workflow is **opt-in**: only run it when the user says
"implement with agents" / "ทำตามแผน โดยใช้ agents" (or for a clearly large/complex task).
For small tasks, a single context is cheaper — don't fan out.

## The agents

| Agent | Model | Role | Never does |
|-------|-------|------|-----------|
| `researcher` | haiku | Codebase + external lookup; returns facts + `file:line`/URLs | Edit code |
| `builder` | sonnet | Implements one planned task under mandatory TDD + uber-go/google style | Touch `CONTEXT.md`, git, or docker |
| `verifier` | inherit (= Main's model) | Outsider review; gets task + result but NOT the requirements chat | Edit or fix anything |
| `super-advisor` | opus | Fresh-context judgment call on a decision/tradeoff | Implement anything |
| `Explore` | built-in | Broad read-only fan-out search | — |
| `Plan` | built-in | Architecture / implementation-plan design | — |

## How Main orchestrates

1. **Grill + design** — clarify requirements with the user (grilling / brainstorming skills)
   until decisions and unknowns are resolved. Token bloat lives here if the brief is fuzzy —
   resolve it before dispatching.
2. **Plan** — hold the plan (DAG: what depends on what) in Main's context. No need to write it
   to disk unless the user wants it. Use `superpowers:writing-plans` for large work.
3. **Research** (as needed) — dispatch `researcher` for lookups so Main doesn't burn top-model
   tokens on grep/reading.
4. **Build** — dispatch `builder` per independent task. Parallelize with
   `superpowers:dispatching-parallel-agents` when tasks share no state; use worktree isolation
   if they'd edit the same files.
5. **Verify** — dispatch `verifier` with ONLY the task statement + the diff. Do not paste the
   requirements conversation (that reintroduces bias).
6. **Loop guard** — Build↔Verify is capped at **2 rounds**. If the second verify still fails,
   stop and escalate to the user rather than spinning. Endless agent-to-agent chatter is the
   token leak to avoid.
7. **Integrate** — after Verifier PASSes, **Main** (not Builder) updates `CONTEXT.md`, commits,
   and rebuilds docker per the repo rules. Builders stay out of `CONTEXT.md`/git to avoid
   parallel-edit conflicts.

## When to call super-advisor
Any autonomous judgment call — an architectural fork, "should we do X", a risky tradeoff —
consult `super-advisor` first for an unbiased read. It advises; Main still decides.
