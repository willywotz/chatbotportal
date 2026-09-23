# Backend Feature Slices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `backend/app` from technical layers into 8 feature slices plus a shared `core/` kernel, with behavior byte-identical.

**Architecture:** `git mv` every module to its feature home (history kept), then rewrite all `app.*` import paths across `backend/` with a mapping-driven helper. `core/` holds infra glue, the security guard, the outbox, and multi-writer tables; `features/<slice>/` hold their own `routers/services/repositories/schemas/models`. `main.py` and `scheduler.py` stay composition roots. `core/registry.py` keeps `Base.metadata` whole so Alembic reports no diff.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-09-23-backend-feature-slices-design.md` (read it — the per-feature file-mapping tables are the authoritative move list; this plan drives them slice by slice).

**Execution deviations (recorded during implementation):**
- The move + import-rewrite was run as **one scripted, deterministic pass** (mapping-driven `git mv` + import rewriter) rather than nine per-slice commits. A global import rewrite cannot be cleanly split into per-slice commits; the script is re-runnable from the scaffold commit, so correctness was gated by `import app.main` + full-suite parity instead of per-slice suites. Rename detection keeps history.
- **Test files keep their current paths.** Relocating ~168 tests into `tests/features/<slice>/` is organizational-only (the root `conftest.py` applies to every subdir, so pass/fail is unchanged), high-churn, and ambiguous for cross-cutting tests. The production `app/` tree is what "feature-based clean architecture" governs; it is fully sliced. Test relocation is a separate, optional pass. The unused `tests/features/` scaffold was removed.

## Global Constraints

- Behavior byte-identical: no route, status code, JSON body, scope, or migration change.
- Structural reorg only: no repository ports, no pure-entity rewrite, no new domain events.
- Files move with `git mv` (never delete+create) so history is kept.
- No compatibility shims: every `app.*` import (in `app/`, `tests/`, `alembic/`, `scripts/`) is rewritten to the new path.
- Self-documenting code, no comments except Swagger/OpenAPI. Simplified Technical English in docs.
- Branch `refactor/backend-feature-slices`; commit one slice at a time.
- Run everything from `backend/` with `uv run`.

## Review Focus

- **Alembic drift:** a moved model that `core/registry.py` fails to import would silently drop a table from `Base.metadata` → autogenerate diff or lost migration. Pinned by Task 11 (`alembic revision --autogenerate` must report no diff) and Task 1 (registry imports asserted).
- **Route table drift:** a router missed in `main.py` re-wiring changes the live surface. Pinned by `tests/test_route_audit.py` after every slice and Task 11.
- **Circular import:** a former flat module now under a feature that another feature imports. Pinned by `python -c "import app.main"` after every slice.
- **Non-`app/` importers:** `alembic/env.py`, `alembic/versions/*`, `scripts/*`, `app/scheduler.py`, MCP mount. Pinned by the tree-wide grep gate in each task and Task 11 boot check.
- **Test patch targets:** `mock.patch("app.services.…")` strings break silently (patch a non-existent path → test passes wrongly or errors). Pinned by the helper rewriting dotted strings too, and the full suite after each slice.

---

## Task 0: Scaffold packages and the reorg helper

**Files:**
- Create: `backend/app/core/__init__.py`, `backend/app/core/{security,models,repositories,utils}/__init__.py`
- Create: `backend/app/features/__init__.py` and `backend/app/features/<slice>/__init__.py` (+ `routers/services/repositories/schemas/models/__init__.py`) for all 8 slices
- Create: `/tmp/.../scratchpad/reorg.py` (helper, NOT committed)
- Create: `backend/tests/features/__init__.py` and per-slice test dirs

**Interfaces:**
- Produces: `reorg.py` exposing `move(pairs)` — takes `[(old_rel, new_rel), …]`, runs `git mv`, records the derived old→new dotted-module map; and `rewrite()` — rewrites every `.py` under `backend/` for the accumulated module map, handling `import a.b.c`, `import a.b.c as x`, `from a.b.c import …`, `from a.b import leaf` (splitting a multi-name line whose names map to different new packages), and bare dotted strings (`"a.b.c"`).

- [ ] **Step 1: Create the directory tree with empty `__init__.py`**

```bash
cd backend
for d in core core/security core/models core/repositories core/utils features \
  features/identity features/settings features/llm features/onechat \
  features/chat features/agency features/mcp features/analytics; do
  mkdir -p app/$d; touch app/$d/__init__.py; done
for f in identity settings llm onechat chat agency mcp analytics; do
  for s in routers services repositories schemas models; do
    mkdir -p app/features/$f/$s; touch app/features/$f/$s/__init__.py; done; done
mkdir -p app/features/identity/oidc && touch app/features/identity/oidc/__init__.py
for f in identity settings llm onechat chat agency mcp analytics; do
  mkdir -p tests/features/$f; touch tests/features/$f/__init__.py; done
touch tests/features/__init__.py
```

- [ ] **Step 2: Write the reorg helper** (`scratchpad/reorg.py`)

```python
import re, subprocess, sys
from pathlib import Path

BACKEND = Path(__file__).resolve()  # set to backend/ at runtime via arg
MODULE_MAP: dict[str, str] = {}

def _dotted(rel: str) -> str:
    return rel[:-3].replace("/", ".") if rel.endswith(".py") else rel.replace("/", ".")

def move(root: Path, pairs: list[tuple[str, str]]):
    for old, new in pairs:
        (root / new).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", old, new], cwd=root, check=True)
        MODULE_MAP[_dotted(old)] = _dotted(new)

def _rewrite_text(text: str) -> str:
    keys = sorted(MODULE_MAP, key=len, reverse=True)
    def sub_from(m):
        pkg, names = m.group(1), m.group(2)
        groups: dict[str, list[str]] = {}
        for name in [n.strip() for n in names.split(",")]:
            full = f"{pkg}.{name}"
            if full in MODULE_MAP:
                np = MODULE_MAP[full].rsplit(".", 1)
                groups.setdefault(np[0], []).append(np[1])
            else:
                groups.setdefault(MODULE_MAP.get(pkg, pkg), []).append(name)
        return "\n".join(f"from {p} import {', '.join(ns)}" for p, ns in groups.items())
    text = re.sub(r"from (app[\w.]*) import ([\w, ]+)", sub_from, text)
    for k in keys:
        text = re.sub(rf"(?<![\w.]){re.escape(k)}(?![\w])", MODULE_MAP[k], text)
    return text

def rewrite(root: Path):
    for py in root.rglob("*.py"):
        if ".venv" in py.parts: continue
        orig = py.read_text()
        new = _rewrite_text(orig)
        if new != orig: py.write_text(new)
```

- [ ] **Step 3: Verify tree compiles as-is (no moves yet)**

Run: `cd backend && uv run python -c "import app.main"` — Expected: no error.

- [ ] **Step 4: Commit scaffold**

```bash
git add backend/app backend/tests && git commit -m "refactor(backend): scaffold feature/core package tree"
```

---

## Task 1: Move the shared kernel (`core/`)

**Files:** move set = the spec's **core** mapping table (config, db, base, errors, concurrency, trace_util, utils/*, usage_context, log_sanitize, events+event_consumers→events, audit, connection_log, security/*, core models event/audit/connection_log, core repos event/audit/connection_log).

**Interfaces:**
- Produces: `app.core.base.Base`, `app.core.db.{get_db,AsyncSessionLocal,engine,init_db,close_db}`, `app.core.errors.{ApiError,register_error_handlers}`, `app.core.security.dependencies.require_scope`, `app.core.security.principal.Principal`, `app.core.events.{publish,dispatch_pending,subscribe}`, `app.core.registry` (imports all model modules).

- [ ] **Step 1: Move core files and rewrite imports**

Feed the core mapping pairs to `reorg.move(...)` then `reorg.rewrite(...)`. Merge `events.py` + `event_consumers.py` into `core/events.py` (concatenate, dedupe imports) — map both old modules to `app.core.events`.

- [ ] **Step 2: Create `core/registry.py`**

```python
import app.core.models.event  # noqa: F401
import app.core.models.audit  # noqa: F401
import app.core.models.connection_log  # noqa: F401
# feature model modules appended as each slice lands (Tasks 2-9)
```

- [ ] **Step 3: Point Alembic at the registry**

Modify `backend/alembic/env.py`: `import app.models` → `import app.core.registry`. Keep `from app.core.base import Base` and `target_metadata = Base.metadata`.

- [ ] **Step 4: Import + boot gate**

Run: `cd backend && uv run python -c "import app.main"` — Expected: no ImportError.
Run tree grep: `grep -rEn "app\.(config|db|errors|concurrency|trace_util|utils|services\.(usage_context|log_sanitize|events|event_consumers|audit|connection_log)|auth)" app tests alembic scripts | grep -v "app.core"` — Expected: empty.

- [ ] **Step 5: Full suite**

Run: `cd backend && uv run pytest -q` — Expected: same pass count as baseline.

- [ ] **Step 6: Commit**

```bash
git commit -am "refactor(backend): extract shared core kernel"
```

---

## Tasks 2-9: Move each feature slice

Each task follows the identical shape below; the only differences are the slice's move set (spec mapping table) and the registry line appended. Order: **2 identity → 3 settings → 4 llm → 5 onechat → 6 chat → 7 agency → 8 mcp → 9 analytics** (dependency order; a later slice may import an earlier slice's model only where a cross-feature FK already exists, which the registry import order satisfies).

Per slice:

- [ ] **Step 1: Move the slice's test files** into `tests/features/<slice>/` (`git mv`), so the parity contract travels with the code.
- [ ] **Step 2: Move the slice's source files** via `reorg.move(...)` using the spec's mapping table for that slice, then `reorg.rewrite(...)`.
- [ ] **Step 3: Append the slice's model modules to `core/registry.py`** (e.g. identity → `import app.features.identity.models.user`, `…oauth`, `…signing_key`).
- [ ] **Step 4: Re-wire `main.py`** — update the feature-router imports and keep the exact same `include_router(..., prefix="/api/v1")` order. For `mcp` also keep the `app.mount("/mcp", …)` line pointing at `app.features.mcp.server`. For `identity` keep the OIDC `app.include_router(oidc_router)` line.
- [ ] **Step 5: Re-wire `scheduler.py`** if the slice owns a job (agency jobs, analytics brief/popular-questions, chat none) — update imports only, same registrations.
- [ ] **Step 6: Import + boot gate** — `uv run python -c "import app.main"`; then grep the tree for any surviving old dotted path for this slice's modules → expect empty.
- [ ] **Step 7: Full suite** — `uv run pytest -q`; expect same pass count. If a `mock.patch("app.<old>…")` string slipped through, the helper's string rewrite missed it → fix the literal, re-run.
- [ ] **Step 8: Route audit** — `uv run pytest tests/test_route_audit.py -q` → pass.
- [ ] **Step 9: Commit** — `git commit -am "refactor(backend): move <slice> into feature slice"`.

Slice-specific notes:
- **identity:** OIDC provider files → `features/identity/oidc/`; the guard (`principal/scopes/dependencies/tokens`) already moved to `core/security` in Task 1, so identity imports it from core. Identity fills the public-key cache at startup exactly as before (no code change, only import path).
- **chat:** largest slice; `services/chat/*` + `conversation/message/similarity` + `schemas/{chat,conversation,responses,openai_conversations}`; single `models/conversation.py` holds both `Conversation` and `Message`.
- **agency:** `services/seed.py` (`run_seed_agencies`) belongs here; `main.py` startup seed import updates to `app.features.agency.services.seed`.
- **analytics:** its `audit_log` and `connection_logs` routers read via `core.audit` / `core.connection_log` (no model ownership here).

---

## Task 10: Remove the emptied layer folders

**Files:** delete now-empty `app/models`, `app/repositories`, `app/routers`, `app/schemas`, `app/services`, `app/auth`, `app/utils` (originals) and any leftover `__init__.py`.

- [ ] **Step 1: Confirm empty** — `find app/models app/repositories app/routers app/schemas app/services app/auth -name "*.py" ! -name "__init__.py"` → expect empty (all moved).
- [ ] **Step 2: Remove** the empty dirs with `git rm -r`.
- [ ] **Step 3: Import + full suite** — `uv run python -c "import app.main"` and `uv run pytest -q` → green.
- [ ] **Step 4: Commit** — `git commit -am "refactor(backend): drop emptied layer packages"`.

---

## Task 11: Final regression gates

- [ ] **Step 1: Alembic no-diff** — `cd backend && uv run alembic upgrade head` then `uv run alembic revision --autogenerate -m "verify no drift"`; open the generated file — it must have empty `upgrade()`/`downgrade()`. Then `git checkout` (discard) that throwaway revision. Expected: no schema operations.
- [ ] **Step 2: Route audit + full suite** — `uv run pytest -q` all green; `tests/test_route_audit.py` green.
- [ ] **Step 3: Boot** — `uv run uvicorn app.main:app --port 8099 &` then `curl -sf localhost:8099/api/v1/... ` a public route; kill it. Expected: 2xx, no ImportError in logs. (Skip if DB not available; the import gate in Step 2 covers wiring.)
- [ ] **Step 4: Tree grep** — `grep -rEn "from app\.(models|repositories|routers|schemas|services|auth) |import app\.(models|repositories|routers|schemas|services|auth)" app tests alembic scripts` → empty.
- [ ] **Step 5: Update `MEMORY.md`** — overwrite Current Focus to this refactor; add an Architectural Boundaries line: "backend = `app/core` kernel + `app/features/<slice>`; dependency rule feature→core only; `core/registry.py` owns `Base.metadata`." Purge the completed `refactor/frontend-to-web` focus.
- [ ] **Step 6: Commit** — `git commit -am "docs(memory): record feature-slice backend layout"`.

---

## Self-Review

**Spec coverage:** every spec mapping table (core + 8 slices) maps to a task (Task 1, Tasks 2-9). Model registry → Task 1 Step 2 + per-slice Step 3. Alembic rewire → Task 1 Step 3. Import-rewrite/no-shims → Task 0 helper + per-slice Step 2. Folder removal → Task 10. All regression gates (suite, route audit, alembic no-diff, boot, tree grep) → Task 11. MEMORY.md → Task 11 Step 5. No gaps.

**Placeholder scan:** the helper and commands are concrete; per-slice move sets are delegated to the spec's authoritative mapping tables (spec travels with the plan) rather than repeated, which is intentional DRY, not a placeholder.

**Type consistency:** `reorg.move`/`reorg.rewrite`/`MODULE_MAP` names are consistent across Task 0 and Tasks 1-9. `core/registry.py`, `Base.metadata`, `require_scope` names match the spec.

**Review Focus:** the five failure modes above each name their pinning gate; none is left uncovered.
