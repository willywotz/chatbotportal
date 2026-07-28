from node:22-alpine as base
env PNPM_HOME="/pnpm"
env PATH="$PNPM_HOME:$PATH"
run corepack enable

workdir /app
copy package.json package-lock.json pnpm-lock.yaml pnpm-workspace.yaml ./
run --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

from base as development
copy . .
cmd ["pnpm", "run", "dev", "--host", "--port", "8080"]

from base as builder
copy . .
run --mount=type=cache,target=/app/node_modules/.vite pnpm run build

from nginx:alpine as production
copy --from=builder /app/dist /usr/share/nginx/html
copy nginx.conf /etc/nginx/conf.d/default.conf
