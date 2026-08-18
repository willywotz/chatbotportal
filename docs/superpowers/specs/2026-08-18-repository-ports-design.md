# Repository Ports (P1) — Design & Template

- Date: 2026-08-18
- Status: Approved (design agreed in session); Conversation is the first template
- Scope: Python backend `backend/app`. Establishes the repository pattern for the
  Clean Architecture P1 work (remove Active-Record coupling from use-case services).

## 1. Problem

The audit's P1 finding: use-case services call the Tortoise ORM directly
(Active-Record) — ~37 service files, ~140 call sites, no repository/port seam,
and ORM exceptions (`tortoise.exceptions.DoesNotExist`) leak into services.

## 2. Key decisions (locked)

1. **Command repositories only.** Repositories isolate the ORM for *use-case
   persistence* (write side + the simple entity reads core services need).
   **Analytics/reporting stays a read-model** that may keep using the ORM/raw
   SQL — reporting legitimately depends on the DB and is not domain logic
   (CQRS-lite). Do not force analytics aggregates or raw pg_trgm SQL behind a
   domain repository.
2. **No `Protocol` yet.** One Tortoise implementation, and tests already run
   against real SQLite (`tests/conftest.py`). A one-implementation interface
   violates the repo's Lazy rule ("no interface with one implementation"). The
   repository *module's* function signatures are the seam; extract a `Protocol`
   only when a second implementation appears (e.g. the Go port). This resolves
   the Clean-Arch-vs-Lazy tension the way the project's rules rank it.
3. **Repositories return/accept Tortoise model instances** (`withinlazy`
   ceiling). They isolate the ORM *operations and exceptions* out of services,
   not the model *type*. Full entity mapping (plain dataclasses) is a later
   step, only if a second backend needs it.
4. **Incremental, one aggregate per branch.** `Conversation` first (clean,
   central). Each later aggregate copies this template. A branch makes only its
   aggregate's *command* access ORM-free; a file may still touch other models
   until their repositories land.

## 3. Layering

New package `app/repositories/`. It is the data-access (infrastructure) layer.
Use-case services import from `app/repositories/`; they stop calling
`Model.get/filter/create/save/delete` and stop importing ORM exceptions.

## 4. The template — `app/repositories/conversation.py`

Module of async functions (the Tortoise adapter). Public surface, derived from
the real command-side call sites (analytics counts excluded on purpose):

```python
async def by_id(conversation_id, *, exclude_deleted=False) -> Conversation | None
async def list_and_count(*, user_id, title_contains, agency_contains,
                         created_from, created_to, offset, limit) -> tuple[list[Conversation], int]
async def create(**fields) -> Conversation
async def save(conv, *, update_fields=None) -> None
async def delete(conv) -> None            # hard delete — preserves today's behavior
```

Semantics:
- `by_id`: `exclude_deleted=True` adds `deleted_at=None`. Returns `None` when
  absent — callers raise their own domain error. No `DoesNotExist` leaves the
  repository.
- `list_and_count`: builds the filtered queryset (`deleted_at=None`, optional
  `user_id`, `title__icontains`, `agencies__contains`, `created_at__gte/__lt`),
  returns `(rows, total)`; ordering is `-created_at`; paging applied only when
  `limit is not None`. Callers pass already-parsed criteria — date validation
  and the admin→`user_id` decision stay in the use-case.
- `create(**fields)`: thin pass-through to `Conversation.create(**fields)`.
- `save(conv, update_fields=None)`: `await conv.save(update_fields=update_fields)`.
- `delete(conv)`: `await conv.delete()` (hard delete).
- Repository functions are transaction-agnostic — they run on Tortoise's ambient connection, so when a use-case wraps calls in `async with in_transaction():` the repository operations join that same transaction; repositories must NOT open their own transactions.

## 5. Service refactor (this branch)

Route Conversation command access through the repository:

| Site | Before | After |
|---|---|---|
| `conversation.py:_authorize` | `Conversation.get_or_none(id, deleted_at=None)` | `by_id(id, exclude_deleted=True)` |
| `conversation.py:delete_conversation` | `Conversation.get(id)` + `except DoesNotExist` → 404 | `by_id(id)`; `if None: raise ApiError(NOT_FOUND, 404)`; then `delete(conv)` |
| `conversation.py:list_conversations` | inline `qs = Conversation.filter(...)` … `.count()` / paging | `list_and_count(...)` (service keeps date-parse validation + admin→user_id) |
| `conversation.py:create_conversation` | `Conversation.create(...)` | `create(...)` |
| `chat/turn.py:save_turn` | `Conversation.get(id)` + `except`→`create`; `conv.save()` | `by_id(id)`; branch to `create(...)` or mutate + `save(conv)` |
| `chat/stream.py:prepare_turn` | `Conversation.get(id)` + `except DoesNotExist`→`ConversationNotFound` | `by_id(id)`; `if None: raise ConversationNotFound(id)` |
| `session.py:ensure_session_warmed` | `conversation.save(update_fields=["external_session_id"])` | `save(conversation, update_fields=["external_session_id"])` |

After this branch, no Conversation site imports `tortoise.exceptions.DoesNotExist`
for Conversation, and no service performs a `Conversation.<orm>` call.

Out of scope this branch (later steps): `Message` access in `conversation.py`
and elsewhere (Message repository), and the analytics `Conversation.filter(
created_at__month...).count()` reads (read-model).

## 6. Testing (TDD)

1. RED: new `tests/repositories/test_conversation_repo.py` exercising `by_id`
   (present / absent / `exclude_deleted`), `list_and_count` (filter + paging +
   total), `create`, `save` (partial `update_fields`), `delete` — fails because
   the module does not exist yet.
2. GREEN: implement `app/repositories/conversation.py`.
3. Refactor each caller to the repository; the existing conversation/chat tests
   stay green (behavior preserved).

## 7. After this template

Apply the same shape to the next aggregates, one branch each: `User`, then
`Agency` (note its atomic `F()`-counter bump → a dedicated `increment_*`
method), then `Message` command-slice (its analytics reads stay in the
read-model). Re-plan each against the tree at that time.
