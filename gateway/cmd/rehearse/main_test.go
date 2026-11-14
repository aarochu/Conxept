package main

import "testing"

func TestResetChecksEffectiveDatabaseHost(t *testing.T) {
	for _, dsn := range []string{
		"postgres://localhost/demo?host=remote.example",
		"postgres://localhost,remote.example/demo",
		"host=remote.example dbname=demo",
	} {
		if err := checkLocal(dsn, false); err == nil {
			t.Errorf("accepted remote reset: %s", dsn)
		}
	}
	for _, dsn := range []string{"postgres://localhost/demo", "host=/tmp dbname=demo"} {
		if err := checkLocal(dsn, false); err != nil {
			t.Errorf("rejected local reset: %v", err)
		}
	}
	if err := checkLocal("postgres://remote.example/demo", true); err != nil {
		t.Fatal(err)
	}
}
