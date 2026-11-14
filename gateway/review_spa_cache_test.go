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
	for _, route := range []string{"/", "/class/demo", "/index.html"} {
		res := httptest.NewRecorder()
		spaFileServer(dir).ServeHTTP(res, httptest.NewRequest("GET", route, nil))
		if (res.Code != 200 && res.Code != 301) || res.Header().Get("Cache-Control") != "no-cache" {
			t.Errorf("%s: %d %v", route, res.Code, res.Header())
		}
	}
}
