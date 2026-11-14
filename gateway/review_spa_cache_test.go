package main

import (
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestRouteShellRevalidation(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "index.html"), []byte("<app-root></app-root>"), 0600); err != nil {
		t.Fatal(err)
	}
	res := httptest.NewRecorder()
	spaFileServer(dir).ServeHTTP(res, httptest.NewRequest("GET", "/class/demo", nil))
	if res.Code != 200 || res.Header().Get("Cache-Control") != "no-cache" {
		t.Fatalf("%d %v", res.Code, res.Header())
	}
}
