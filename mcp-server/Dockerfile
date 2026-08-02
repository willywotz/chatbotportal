from golang:1.26-alpine as base
workdir /app
env GOPATH=/go
env GOCACHE=/root/.cache/go-build
copy go.mod go.sum ./
run --mount=type=cache,target=/go/pkg/mod \
    go mod download

from base as development
copy . .
cmd ["go", "run", "."]

from base as builder
copy . .
run --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /app/mcp-server .

from alpine as production
workdir /app
run apk --no-cache add ca-certificates tzdata wget
copy --from=builder /app/mcp-server /usr/local/bin/mcp-server
entrypoint ["/usr/local/bin/mcp-server"]
