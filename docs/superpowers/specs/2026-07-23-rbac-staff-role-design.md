# RBAC — Add a `staff` Role (Two Roles to Three)

**Date:** 2026-07-23
**Status:** Approved, pending implementation plan

## Goal

Split the low tier of the role model. Today there are two stored roles — `user` and `admin`
(plus anonymous) — where `user` can reach chat, own history, the Architecture list, **and** six
read-only operational dashboards. That role is really a staff/officer role (the frontend login is
already labelled **เข้าสู่ระบบเจ้าหน้าที่**, "staff login").

Introduce a genuinely minimal citizen role and rename the current one:

1. **`user`** becomes a new, minimal citizen role: start a new chat, manage own history, and view
   the Architecture list. Nothing else.
2. **`staff`** is today's `user` role renamed — it keeps every path it can reach today.
3. **`admin`** is unchanged.

Existing accounts with `role = 'user'` migrate to `staff`, so no current officer loses access.
New accounts default to the least-privileged `user`.

This is the deliberate re-split foreseen by `2026-07-23-rbac-simplification-design.md`: that
change collapsed five roles to two on the premise that self-registration was gone and a `user`
reaching dashboards was therefore acceptable. A truly minimal `user` role is the precondition for
citizen self-service, which is left as a follow-up (see Non-goals).

## Role model

| Role | Definition | Reaches |
|---|---|---|
| anonymous | No bearer token. Not a stored value. | `GET /api/v1/public/*`, `GET /api/v1/agencies/{id}/logo`, optional-auth chat. **Unchanged.** |
| `user` | New minimal citizen role. Default for every account. | Shared writes (chat, `/responses`, message rating, all verbs on own `/conversations`, `/auth/*`) + `GET /conversations/{id}/messages` + `GET /api/v1/agencies` (Architecture list). **No ops dashboards.** |
| `staff` | Today's `user` role, renamed. | Everything `user` reaches **plus** the six read-only ops dashboard GETs. Identical to the pre-split `user` surface. |
| `admin` | Everything. **Unchanged.** | — |

Strict nesting: `user` ⊂ `staff` ⊂ `admin`. The **only** difference between `user` and `staff`
is the six-entry dashboard GET set (`_STAFF_GET_EXACT` below).

### The invariant

Authorization reduces to four rules:

1. **Anonymous** — unchanged.
2. **`user`** reaches: all `/api/v1/auth/*`; `POST /api/v1/chat`, `/chat/stream`, `/responses`;
   `PATCH /api/v1/messages/{id}/rating`; all verbs on `/api/v1/conversations` and
   `/conversations/{id}`; `GET /conversations/{id}/messages`; and `GET /api/v1/agencies`.
3. **`staff`** reaches everything in rule 2 **plus** the six dashboard GETs:
   `/dashboard/stats`, `/executive-summary`, `/agency-health`, `/usage-heatmap`,
   `/insight/usage`, `/feedback/stats`.
4. **`admin`** reaches everything.

**`staff`'s reachable set equals the pre-split `user` set, exactly.** The new `user`'s set is
that minus the six dashboards. This is the checkable claim the surface-parity test enforces.

## Backend changes

### Chokepoint (`app/auth/dependencies.py`)

- Rename constant `_BASIC_USER_GET_EXACT` → `_STAFF_GET_EXACT` (same six dashboard paths, now a
  staff-only grant). Update its docstring: these are staff read-only dashboards, not basic-user.
- `_is_allowed_for_basic_user` (role `user`) drops the `_BASIC_USER_GET_EXACT` clause. It becomes:
  shared writes, `GET /api/v1/agencies` (Architecture list), and the conversation-messages GET.
- New `_is_allowed_for_staff`:

  ```python
  def _is_allowed_for_staff(method: str, path: str) -> bool:
      """Role ``staff``: everything a basic user can do, plus read-only ops dashboards."""
      if _is_allowed_for_basic_user(method, path):
          return True
      return method == "GET" and path in _STAFF_GET_EXACT
  ```

- `_ROLE_ALLOWLIST = {"user": _is_allowed_for_basic_user, "staff": _is_allowed_for_staff}`.
- The unknown-role fallback in `enforce_role_allowlist` stays `_is_allowed_for_basic_user`. This
  remains deny-by-default and least-privilege: a residual/unknown role can reach only chat,
  own-history, and the Architecture list — never a dashboard or a privileged write. The
  `admin`/anonymous pass-through escape hatch is untouched.

### Schema (`app/schemas/user.py`)

`Role` becomes `Literal["user", "staff", "admin"]`. The `User.role` column stays
`CharField(max_length=20, default="user")` — no column change, only what the schema layer accepts.
The create/update API 422s on any other value.

### No new endpoint guard

The six dashboard endpoints carry **no** `require_admin` today (they are reachable by the current
`user`). They stay ungated at the endpoint level; the chokepoint alone now restricts them to
`staff` + `admin`. No `require_staff` dependency is introduced — nothing needs a "staff-or-above"
per-endpoint check.

## Frontend changes

`features/auth/roles.ts`:

- `Role` becomes `"user" | "staff" | "admin"`.
- `ROUTE_ROLES`: `/chat`, `/history`, `/architecture` → all three roles; the six dashboard routes
  (dashboard, executive, agency-health, heatmap, usage/insight, feedback) →
  `["staff", "admin"]`; every other entry stays `["admin"]`.

`App.tsx`: the `ProtectedRoute` group that currently admits `user` to the dashboard pages changes
to admit `staff` + `admin`. `/chat`, `/history`, `/architecture` remain open to any authenticated
role.

`features/users/roleLabels.ts`: add `staff: "เจ้าหน้าที่"`, keep `user: "ผู้ใช้"` and
`admin: "ผู้ดูแลระบบ"`. `UserFormDialog`'s role dropdown and `UsersPage`'s role filter read from
this map, so both update for free. The dropdown's default selection is `user`.

The sidebar (`shared/components/layout/AppSidebar.tsx`) needs no change — it filters `navItems`
through `canAccess(user.role, item.url)` and picks up the new `ROUTE_ROLES`. A logged-in `user`
simply sees fewer items (Chat, History, Architecture). No new layout: `user` uses the same
`AppLayout` shell as `staff`.

The public portal's login control is relabelled from **เข้าสู่ระบบเจ้าหน้าที่** ("staff login") to
**เข้าสู่ระบบ** ("login"), since the login now serves citizens as well as staff. Two source sites:
`features/public/PublicPortal.tsx` and `features/public/InfoPage.tsx`. (The `frontend/dist/`
occurrences are build artifacts and regenerate on build — not edited by hand.)

Any component still gating on a two-role assumption (e.g. treating "not admin" as "read-only
dashboard viewer") is reviewed during implementation; the canonical gate is `canAccess` /
`ROUTE_ROLES`, not ad-hoc role checks.

## Migration

A single aerich migration, **generated** via `aerich migrate` against an upgraded DB. Per
`CLAUDE.md`, `MODELS_STATE` is never hand-carried.

There is no column change (the default is already `"user"` and stays so). Aerich does not generate
data changes, so one statement is hand-added to the generated `upgrade()`:

```sql
UPDATE users SET role = 'staff' WHERE role = 'user';
```

Existing `user` rows — the pre-split officers — become `staff`. `admin` rows are untouched. New
accounts continue to default to `user`, which is now the least-privileged role.

**This migration is irreversible for role identity.** `downgrade()` cannot know which post-migration
`staff` rows were `user` before the split versus already-existing staff, so it cannot restore the
prior distribution. The migration docstring states this plainly rather than implying a clean
rollback.

## Testing

TDD throughout, per `CLAUDE.md`. Tests are written before the code they cover.

**Written first — the surface-parity test.** A test enumerates every `(method, path)` pair
reachable by `user`, by `staff`, and by anonymous, asserting the full set for each. Two anchored
assertions make the split checkable:

- `staff`'s reachable set equals the pre-split `user` set (captured from the current code before
  the change).
- the new `user`'s set equals `staff`'s set minus the six dashboard GETs.

**Rewritten:**

- `tests/test_basic_user_allowlist.py` — `user` no longer reaches the six dashboards; still reaches
  chat, own-history verbs, conversation-messages GET, and `GET /agencies`.
- `tests/test_user_schema_roles.py` — accepts `user`, `staff`, `admin`; rejects anything else (422).

**New:**

- a staff-allowlist test asserting `staff` reaches the six dashboards **and** everything a `user`
  can, and nothing admin-only.

**Frontend:** `roles.test.ts`, `ProtectedRoute.test.tsx`, `roleLabels.test.ts`,
`UsersPage.test.tsx` updated for the three-role model. Dashboard-page route tests assert a `user`
is blocked while `staff` and `admin` are allowed.

## Non-goals

- **Public self-registration.** Re-adding `POST /api/v1/auth/register` and a `/signup` page,
  hardcoded to create `role = 'user'`, is a separate follow-up spec with its own security review
  (rate-limiting, abuse). This round is admin-created accounts only; the admin user form gains
  `user` as an assignable minimal role.
- **A distinct citizen UI.** `user` uses the same authenticated `AppLayout` with a role-filtered
  sidebar. No stripped-down or separate shell.
- **Inverting the chokepoint to per-endpoint declaration.** Still the right end state, still
  separable, still out of scope.
- **Any unrelated refactoring** of the routers or components being touched.

## Documentation to update

- `CONTEXT.md` — the "Auth & RBAC" section (roles list and chokepoint description) and the `User`
  row in the data-model table (`role = user|staff|admin`). Note the self-registration follow-up.
