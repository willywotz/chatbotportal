# Project Rule
- Reply in ASD-STE100 Simplified Technical English
- when user tell to write handoff must write at `docs/HANDOFF.md` only
- use TDD Mandatory : Red (write failing test) -> Green (write minimal code to pass) -> Refactor (strict).
- use Branching Mandatory : Always branch (git checkout -b <type>/<desc>) before multi-task work; never commit directly to main.
- Worktree Off : git worktree is disabled/denied — never create or enter a worktree; use a plain branch (git checkout -b) only.
- must strictly comply with the 15-Factor App methodology
- API endpoint routes use full English words — no short forms or aliases.
- Code style: write self-documenting code. Use clear, descriptive names for variables and functions so the code explains itself. Do not write comments. The only allowed comments are Swagger/OpenAPI documentation.

# Role & Context Memory Strict Enforcement Rule

You must actively maintain, prune, and strictly synchronize the project's root context memory file (`MEMORY.md`). Treat this file as the absolute, living source of truth for repository state, architectural decisions, and current progress.

## 1. Zero-Assumption Initialization (Start of Every Session/Task)
* **Read First**: Always inspect `MEMORY.md` before analyzing code, planning, or writing implementations.
* **Sync Check**: Cross-check `MEMORY.md` with recent Git commits or file changes. If the codebase diverged from what `MEMORY.md` claims, reconcile the file immediately.

## 2. Hard Gate: "Definition of Done"
No task or debugging session is marked complete until `MEMORY.md` reflects the state of your changes. Updating memory is **not an optional post-task action**; it is the final mandatory step before concluding any response.

Trigger an update immediately when:
- Any task item moves from pending `[ ]` to done `[x]`.
- A new blocker, dependency, or edge case/gotcha is discovered.
- An architectural pattern, database schema, or environment variable changes.
- The `Current Focus` shifts to a new scope or next steps.

## 3. Strict Synchronization & Anti-Rot Protocol
When modifying `MEMORY.md`, apply this checklist to keep data accurate and fresh:
- [ ] **Current Focus**: Overwrite completely with the exact next actionable step. Never leave past tasks here.
- [ ] **Active Status**: Update checklist states; append newly discovered sub-tasks.
- [ ] **Lessons Learned / Pitfalls**: Add single-line operational notes. Prune temporary workarounds once a permanent fix is merged.
- [ ] **Architectural Boundaries**: Log any newly adopted conventions, schema shifts, or banned libraries.

## 4. Garbage Collection (Pruning Rotten Context)
Do not let `MEMORY.md` become an append-only graveyard. Actively purge stale information during updates:
* **Purge Solved Tasks**: Delete completed `[x]` items once the task phase or git commit is finalized. Only retain the current active milestone's pending items.
* **Deprecate Expired Blockers**: Immediately remove blockers, temporary hacks, or warnings for dependencies/bugs that have been resolved or upgraded.
* **Invalidate Stale Assumptions**: If an architectural decision or rule is superseded by new requirements, overwrite or remove it—never keep conflicting legacy rules.
* **Keep Token Density High**: Target under ~100–150 lines. If the file expands beyond that, aggressively summarize or prune historical notes that are already captured in Git history.

## 5. Enforcement Constraints
* **Atomic Edits**: Update in-place with precise diffs; do not wipe active sections unprompted.
* **Punchy & Dense**: Zero conversational commentary, intros, or summaries inside `MEMORY.md`. Use bullet points, code tags, and markdown checkboxes only.
* **Explicit Acknowledgment**: In your final response to the user, include a brief 1-line confirmation stating what was added, updated, or purged in `MEMORY.md`.
