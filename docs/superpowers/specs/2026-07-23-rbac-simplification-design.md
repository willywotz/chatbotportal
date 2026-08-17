# RBAC Simplification — Five Roles to Two

**Date:** 2026-07-23
**Status:** Approved, pending implementation plan

## Goal

Collapse the role model from five roles (`user`, `viewer`, `auditor`, `agency_owner`, `admin`)
to two stored roles (`user`, `admin`) plus anonymous, and delete the authorization machinery
that existed only to serve the three removed roles.

Two motivations, both stated by the user:

1. **Too complex to reason about.** Five roles crossed with a global allowlist chokepoint and
   a three-layer RBAC/ReBAC/ABAC engine is hard to hold in one's head and easy to get wrong.
2. **Nobody uses them.** `viewer`, `auditor`, and `agency_owner` were built speculatively; the
   real deployment has citizens and admins.

Because the motivation is complexity rather than a behavior change, the guiding constraint is:
**no surviving caller's access changes.** This is a deletion, not a redesign.

## Role model

| Role | Definition |
|---|---|
| anonymous | No bearer token. Not a stored value. |
| `user` | Default for every account. Citizen-facing surface only. |
| `admin` | Everything. |

`Role` in `backend/app/schemas/user.py` becomes `Literal["user", "admin"]`. The `User.role`
column stays a `CharField(max_length=20, default="user")` — no schema change to the column
itself, only to what the schema layer accepts.

### The invariant

Authorization reduces to three rules:

1. **Anonymous** reaches `GET /api/v1/public/*`, `GET /api/v1/agencies/{id}/logo`, and the
   optional-auth chat surface. Unchanged.
2. **`user`** reaches exactly what `_is_allowed_for_basic_user` allows today: all `/api/v1/auth/*`;
   `POST /api/v1/chat`, `/api/v1/chat/stream`, `/api/v1/responses`;
   `PATCH /api/v1/messages/{id}/rating`; all verbs on `/api/v1/conversations` and
   `/api/v1/conversations/{id}`; and `GET /api/v1/agencies`. Unchanged.
3. **`admin`** reaches everything.

Every page and endpoint not named in rules 1–2 becomes admin-only. This is "keep as is" from the
surviving roles' point of view: no account that exists after the migration gains or loses a
single path relative to what its role could reach before.

## Backend changes

### Chokepoint (`app/auth/dependencies.py`)

`_ROLE_ALLOWLIST` reduces to a single `user` entry. `enforce_role_allowlist` keeps its shape but
now has one meaningful branch. Deleted: `_is_allowed_for_viewer`, `_is_allowed_for_auditor`,
`_VIEWER_GET_EXACT`, `_VIEWER_GET_PATTERN`, `_SETTINGS_PREFIX`.

The `check is None → pass through` escape hatch now applies only to `admin` and anonymous. This
narrows the standing hazard — that a new endpoint which forgets its own guard is reachable by a
non-admin role — down to nothing, since the only role that passes through is the one entitled to
everything anyway. Closing it properly (inverting to per-endpoint declaration) is deliberately
**out of scope**; see Non-goals.

`require_admin_or_auditor` is deleted and its 16 call sites move to `require_admin`:
`routers/audit_log.py`, `routers/connection_logs.py`, `routers/llm.py`,
`routers/popular_questions.py`, `routers/users.py`.

### `app/auth/authz.py` — deleted in full

The file is removed: `Decision`, `authorize`, `authorize_or_403`, `grant`, `has_relation`,
`_abac`, `_log`, `_ADMIN_ONLY`, `_AUDITOR_READ`, `_RELATION_FOR`.

All 15 `authorize_or_403` call sites collapse:

| Call site | Action | Becomes |
|---|---|---|
| `routers/agencies/crud.py` (3) | `agency:edit` ×2, `agency:delete` | `Depends(require_admin)` |
| `routers/agencies/golden.py` (4) | `agency:edit` | `Depends(require_admin)` |
| `routers/agencies/lifecycle.py` (2) | `agency:change_status`, `agency:edit` | `Depends(require_admin)` |
| `routers/agencies/logo.py` (1) | `agency:edit` | `Depends(require_admin)` |
| `routers/feedback.py` (1) | `agency:read_logs` | `Depends(require_admin)` |
| `routers/agencies/owners.py` (1) | `user:manage` | file deleted |
| `routers/conversations.py` (3) | `conversation:read` ×2, `conversation:delete` | inline own-or-admin check |

The conversations check is written inline at each of the three sites rather than extracted into a
helper — three uses in one file do not justify an abstraction layer:

```python
if str(conv.user_id) != str(user.id) and not user.is_admin:
    raise HTTPException(status_code=403, detail="Forbidden")
```

Two behaviors are removed with the file, both deliberately:

- **`_abac`'s "active agencies are edited via admin approval" rule.** It could only ever fire for
  a non-admin, because `authorize()` short-circuits on `user.role == "admin"` at the RBAC layer
  before reaching ABAC. With agency editing now admin-only, the rule was already unreachable.
  This is **not** the demote-to-draft-on-connection-edit behavior from
  `docs/adr/0002-agency-edit-connection-demote.md` — that lives in the agency update service and
  is untouched.
- **`_AUDITOR_READ`**, which disappears along with the `auditor` role.

### Ownership removal

Deleted: `app/models/relationship.py` (the `Relationship` model) and
`app/routers/agencies/owners.py` (`POST /agencies/{id}/owners`, `GET /agencies/mine`,
`AddOwnerRequest`), plus the corresponding re-exports at the bottom of
`app/routers/agencies/__init__.py`.

`routers/connection_logs.py` loses both owner-scoping blocks (the `user.role == "agency_owner"`
branches around lines 60–65 and 159–164). Both endpoints become plainly admin-scoped, since a
`user` cannot reach them through the chokepoint at all.

`routers/conversations.py:95`'s `if not (user.is_admin or user.role == "auditor")` becomes
`if not user.is_admin`.

## Frontend changes

`features/auth/roles.ts`:

- `Role` becomes `"user" | "admin"`.
- `ROUTE_ROLES` collapses from 22 entries across five tiers to: `/chat` and `/architecture`
  allowing both roles, every other entry `["admin"]`.
- `READ_ONLY_ROLES` and `isReadOnlyRole` are deleted.

Deleting `isReadOnlyRole` cascades. `useAuth().isReadOnly` is consumed by `AgenciesPage`,
`AgencyCard`, `AgencyDetailPage`, and `ApiKeyList`; every page it guards is now admin-only, so the
value is permanently `false`. Each `{!isReadOnly && …}` guard becomes unconditional and the
conditional is removed, including `AgencyDetailPage`'s `defaultTab` read-only fallback. The
`isReadOnly` field is removed from `useAuth` itself.

`App.tsx`'s five nested `ProtectedRoute` groups collapse to one admin group, with `/chat` and
`/architecture` remaining open to any authenticated role.

Deleted: `features/agencies/MyAgenciesPage.tsx` and the `/my-agencies` route, plus the
`/agencies/mine` query hook in `features/agencies/useAgencies.ts` and its client method in
`features/agencies/agencyApi.ts`. These are ownership features with no ownership table behind
them. `/agencies/new` and `/agencies/:id/setup` survive as admin routes.

`features/users/roleLabels.ts` drops three entries, keeping `user: "ผู้ใช้"` and
`admin: "ผู้ดูแลระบบ"`. This automatically shrinks the `UserFormDialog` role dropdown and the
`UsersPage` role filter, which both read from it.

The sidebar (`shared/components/layout/AppSidebar.tsx`) needs no change — it filters `navItems`
through `canAccess(user.role, item.url)` and picks up the new `ROUTE_ROLES` for free.

## Migration

A single aerich migration, **generated** via `aerich migrate` against an upgraded DB.
Per `CLAUDE.md`, `MODELS_STATE` is never hand-carried. It drops the `relationships` table.

Aerich does not generate data changes, so one statement is hand-added to the generated
`upgrade()`:

```sql
UPDATE users SET role = 'user' WHERE role NOT IN ('user', 'admin');
```

Accounts already marked `admin` keep admin. Everyone else becomes a plain `user`. Anyone who
genuinely needs elevated access is promoted deliberately afterward.

**This migration is irreversible.** `downgrade()` can recreate an empty `relationships` table,
but it cannot recover which accounts were previously `viewer`, `auditor`, or `agency_owner`, nor
which agencies they owned. This is inherent to the decision. The migration docstring states it
plainly rather than implying a clean rollback.

## Testing

TDD throughout, per `CLAUDE.md`.

**Written first — the surface-parity test.** Before any deletion, a test enumerates every
(method, path) pair reachable by `user` and by anonymous, asserting the full set. It must pass
identically against the current code and the finished refactor. This is what makes "no surviving
caller's access changes" a checkable claim instead of an aspiration, and it is the safety net for
the entire change.

**Deleted:** `tests/test_authz.py`, `tests/test_agency_owners.py`,
`tests/test_auditor_read_access.py`.

**Rewritten:** `tests/test_role_allowlist.py`, `tests/test_user_schema_roles.py`,
`tests/test_basic_user_allowlist.py` (drops its `agency_owner` case).

**New:** a test asserting the users API rejects `"viewer"`, `"auditor"`, and `"agency_owner"`
with a 422, so the removal cannot silently regress through role assignment.

**Frontend:** `roles.test.ts`, `ProtectedRoute.test.tsx`, `roleLabels.test.ts`,
`UsersPage.test.tsx`, `AppSidebar.test.tsx` are updated for the two-role model;
`AgencyCard.test.tsx` and `AgencyDetailPage.test.tsx` lose their `isReadOnly = true` cases.

## Non-goals

- **Inverting the chokepoint to per-endpoint declaration.** The right end state is that a new
  route is closed until it declares itself open, rather than open unless the allowlist catches it.
  That change touches every router and is separable; this refactor deliberately leaves the
  codebase in a state where it is a clean follow-up.
- **Changing what `user` or anonymous can reach.** Explicitly out of scope — see the invariant.
- **Any unrelated refactoring** of the routers being touched.

## Documentation to update

- `CONTEXT.md` — the "Auth & RBAC" section (roles list, chokepoint description) and the `User` /
  `Relationship` rows in the data-model table.
- `docs/adr/0002-agency-edit-connection-demote.md` — its "Edit tab is gated on `!isReadOnly`
  (admin + agency_owner); backend ReBAC still limits agency_owner to their own agencies" note is
  falsified by this change and needs a superseding note.
