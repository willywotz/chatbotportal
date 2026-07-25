# Hide ephemeral users from admin user management

**Date:** 2026-07-26
**Status:** Approved

## Problem

Anonymous public-portal visitors are persisted as ephemeral accounts
(`User.is_ephemeral = True`). The admin user-management screen calls
`GET /users` (`list_users` in `backend/app/routers/users.py`), which currently
returns **every** user row. Ephemeral temp-users therefore appear mixed in with
real admin/staff accounts, cluttering the list and inflating the total count.

They must be hidden, and the filtering must happen **at the backend level** (in
the query) so the frontend receives a clean list and needs no logic of its own.

## Decision

**Always hide.** `list_users` excludes `is_ephemeral = True` unconditionally.
There is no opt-in flag to surface ephemeral users through this endpoint.

## Change

Single point of change: the base queryset in `list_users`
(`backend/app/routers/users.py`).

```python
qs = User.filter(is_ephemeral=False)
```

All existing filters (`search`, `role`, `status_filter`), ordering, and the
`total` count then operate only over real accounts. `total` is correct because
it is derived from the same filtered rows.

## Scope

- **Only `list_users` changes.** `get_user`, `update_user`, `deactivate_user`,
  and `activate_user` operate by explicit ID and are not reachable from the UI
  for ephemeral users, so they are left unchanged to keep blast radius minimal.
- **No schema/migration change** — `is_ephemeral` already exists on the model.
- **No frontend change** — the user-management view renders whatever
  `GET /users` returns.

## Testing (TDD)

1. **Failing test first:** seed one normal user and one `is_ephemeral=True`
   user; call `GET /users` as an admin; assert the ephemeral user is absent from
   `data` and that `total` counts only the real user.
2. **Regression:** existing `search` / `role` / `status=all` filters still work
   and never surface the ephemeral user.

## Error handling

None new — this is a query narrowing, not a new failure path.
