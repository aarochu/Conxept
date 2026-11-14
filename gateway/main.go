package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/net/http2"
	"golang.org/x/net/http2/h2c"

	"misconception/gen/go/misconception/v1/misconceptionv1connect"
)

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// newMux serves GatewayService at /misconception.v1.GatewayService/ and the built Angular app everywhere else.
func newMux(gw *Gateway, webDir string) *http.ServeMux {
	mux := http.NewServeMux()
	path, handler := misconceptionv1connect.NewGatewayServiceHandler(gw)
	mux.Handle(path, handler)
	mux.Handle("/", spaFileServer(webDir))
	return mux
}

// spaFileServer serves static files and falls back to index.html for client routes.
func spaFileServer(dir string) http.Handler {
	files := http.FileServer(http.Dir(dir))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		clean := filepath.Clean("/" + r.URL.Path)
		full := filepath.Join(dir, filepath.FromSlash(clean))
		if info, err := os.Stat(full); err == nil && !info.IsDir() {
			files.ServeHTTP(w, r)
			return
		}
		if filepath.Ext(clean) != "" && !strings.HasSuffix(clean, ".html") {
			http.NotFound(w, r)
			return
		}
		index := filepath.Join(dir, "index.html")
		if _, err := os.Stat(index); err != nil {
			http.Error(w, "web app not built (expected "+index+")", http.StatusNotFound)
			return
		}
		http.ServeFile(w, r, index)
	})
}

func main() {
	dbURL := env("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/misconception")
	engineAddr := env("ENGINE_ADDR", "http://localhost:50051")
	port := env("PORT", "8080")
	webDir := env("WEB_DIR", "./web")

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	pool, err := pgxpool.New(ctx, dbURL)
	if err != nil {
		log.Fatalf("database: %v", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		log.Fatalf("database: %v", err)
	}
	store, err := NewStore(pool)
	if err != nil {
		log.Fatal(err)
	}

	gw := &Gateway{engine: newEngineClient(engineAddr), agent: newAgentClient(engineAddr), store: store}
	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           h2c.NewHandler(newMux(gw, webDir), &http2.Server{}),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdown)
	}()
	log.Printf("gateway listening on :%s (engine %s, web %s)", port, engineAddr, webDir)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
