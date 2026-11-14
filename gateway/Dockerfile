# Go gateway on :8080, serving the built Angular app from /web.
# Build from the repo root: docker build -f gateway/Dockerfile .

# --- web: generate the TypeScript client and build the Angular app
FROM node:22-slim AS web
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY web/package.json web/package-lock.json web/
WORKDIR /src/web
RUN npm ci
WORKDIR /src
COPY buf.yaml ./
COPY proto proto
RUN npx buf generate --template \
    '{"version":"v2","plugins":[{"local":"node_modules/.bin/protoc-gen-es","out":"web/src/gen","opt":"target=ts"}]}'
COPY web web
WORKDIR /src/web
RUN npx ng build

# --- go: generate the Go stubs and build a static binary
FROM golang:1.27 AS go
# Same buf version as package-lock.json: the static binary npm installed in the web stage.
COPY --from=web /src/node_modules/@bufbuild/buf-linux-*/bin/buf /usr/local/bin/buf
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.12 \
 && go install connectrpc.com/connect/cmd/protoc-gen-connect-go@v1.21.1
WORKDIR /src
COPY gateway/go.mod gateway/go.sum gateway/
WORKDIR /src/gateway
RUN go mod download
WORKDIR /src
COPY buf.yaml ./
COPY proto proto
RUN buf generate --template \
    '{"version":"v2","plugins":[{"local":"protoc-gen-go","out":"gateway/gen/go","opt":"paths=source_relative"},{"local":"protoc-gen-connect-go","out":"gateway/gen/go","opt":"paths=source_relative"}]}'
COPY gateway gateway
COPY sql/queries.sql gateway/queries.sql
WORKDIR /src/gateway
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/gateway .

# --- runtime
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=go /out/gateway /gateway
COPY --from=web /src/web/dist/web/browser /web
ENV WEB_DIR=/web PORT=8080
EXPOSE 8080
ENTRYPOINT ["/gateway"]
