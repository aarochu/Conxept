# gateway (Lane B, Go)

connect-go `GatewayService` on port 8080, serves the built Angular app, owns all DB writes (pgx),
calls the engine over gRPC (h2c). Module name: `misconception`.

First gate (spec §6.2): generate Go stubs, compile an empty handler, make one `Diagnose` call to the
Python engine. If connect-go + `WithGRPC()` over h2c fails, fall back to a `grpc-go` client.

Planned files: `go.mod`, `main.go`, `service.go`, `db.go`. Generated code in `gateway/gen/go/` (not committed).
