package main

import (
	"testing"
	"time"
)

func TestClassDurationGate(t *testing.T) {
	for _, elapsed := range []time.Duration{time.Second, time.Minute} {
		if err := checkClassDuration(elapsed); err != nil {
			t.Fatal(err)
		}
	}
	if err := checkClassDuration(time.Minute + time.Nanosecond); err == nil {
		t.Fatal("over-budget class accepted")
	}
}
