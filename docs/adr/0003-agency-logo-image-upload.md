# 0003 — Agency logo: emoji **or** uploaded image (backend-served, filesystem volume)

Status: Accepted — 2026-07-11

## Context

Agency `logo` was an emoji string (`CharField(max_length=20)`), rendered as raw text
in ~8 places. We want an agency to optionally use an **uploaded image** instead of an
emoji. There is **no upload/storage infrastructure** in the repo (no `UploadFile`,
`StaticFiles`, object store, or static route), and the deployment is a **single-host
`docker compose`** stack fronted by an nginx reverse proxy whose routing contract
(`default.conf`) is treated as a single source of truth.

The decisions were made interactively; the user initially chose nginx-direct static
serving, then — after a super-advisor review flagged the fragility and extra moving
parts — switched to backend-serving.

## Decision

**Store logos on the local filesystem on a named Docker volume; serve them through the
backend; keep a single `logo` field that holds either an emoji or an image URL.**

- **Storage**: files live under an `UPLOAD_DIR` (single config constant) on a **named
  volume** mounted **rw into the backend only**. No nginx change, no cross-container
  mount. Declared in the **base** `compose.yaml` (inherited by the dev override) so
  uploads survive `docker compose up -d --build --remove-orphans`.
- **Serving**: `GET /api/v1/agencies/{id}/logo` streams the file with an explicit
  allowlisted `media_type`, `X-Content-Type-Options: nosniff`, and
  `Cache-Control: public, max-age=31536000, immutable`. This path already matches the
  nginx `^/(api|…)` rule → backend, so **the routing contract is untouched**. Serving
  logos through the backend keeps them inside the existing auth/routing surface (they are
  already publicly exposed via `GET /public/agencies`) rather than punching a parallel
  static subsystem.
- **Upload**: `POST /api/v1/agencies/{id}/logo` (multipart, ReBAC `agency:edit`) —
  validate **PNG/JPEG/WebP by magic bytes + content-type** (SVG excluded: XSS surface),
  **≤512 KB**, write `{id}-{sha256[:8]}.{ext}` to `UPLOAD_DIR`, set
  `agency.logo = /api/v1/agencies/{id}/logo?v={hash}`, return the updated agency. Persists
  immediately (independent of the General section's PATCH).
- **Content-hash filenames** give free cache invalidation: the URL's `?v={hash}` changes
  iff the bytes change, so `immutable` caching is safe with zero staleness. A pre-write
  **glob-delete of `{id}-*`** prevents extension/hash orphans (best-effort; never fails
  the request).
- **Field**: reuse `logo`, **widened `CharField(20 → 255)`** via one aerich migration. It
  holds an emoji or the image URL; the frontend `AgencyLogo` component renders `<img>`
  when the value looks like a path/URL (`/api/`, `/uploads/`, `http`, `data:`) else emoji
  text. Revert to emoji = type one and save the section.
- **Cleanup**: agency delete best-effort removes `{id}-*`. Only two deletion paths exist —
  delete-agency and the pre-write orphan sweep.
- **Scope**: image upload is **Edit-tab only** (needs an agency id; the wizard's first
  step has none). The color picker (ADR-adjacent change) applies to both wizard + edit.

## Alternatives considered

- **nginx-direct static serving** (shared volume ro into nginx + `location /uploads/`).
  Faster static path, but edits the routing contract, adds a second mount + a matching dev
  override mount, and works only because the backend runs as root (nginx uid 101 reads
  root-written 0644 files) — a future non-root hardening PR would silently break it.
  Rejected: too many moving parts and a latent uid coupling for ~8 small images.
- **Object storage (S3/MinIO)**: adds a service + credentials the stack lacks. Rejected.
- **DB BLOB / data URI**: bloats every agency row/response; needs a `TextField`. Rejected.
- **Separate `logo_url` column**: doubles the fields threaded through schemas, form state,
  and all render sites, and needs a precedence + revert rule. Rejected in favor of the
  single widened `logo`.
- **`?v=updated_at` cache-busting** instead of content-hash filenames: relies on every
  consumer remembering to append the query. Rejected for content-hash filenames.

## Consequences

- One named volume is now load-bearing for logo persistence; a `down -v` or a renamed
  volume drops all logos. Backups must include it.
- The backend serves image bytes (negligible at this scale). If logo traffic ever became
  significant, flipping to nginx-direct is possible but would reintroduce the coupling
  above.
- Upload persists immediately, so the frontend **must sync the General section's in-memory
  `logo` after upload** or a subsequent section PATCH will clobber the new path with a
  stale value.
- `UPLOAD_DIR` and the served URL must derive from one config value; two drifting
  hardcoded strings would 404.
