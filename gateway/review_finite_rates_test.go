package main

import (
	"connectrpc.com/connect"
	"context"
	"math"
	v1 "misconception/gen/go/misconception/v1"
	"testing"
)

func TestNonFiniteRates(t *testing.T) {
	for _, v := range []float32{float32(math.NaN()), float32(math.Inf(1)), float32(math.Inf(-1))} {
		for _, req := range []*v1.SeedSyntheticClassRequest{{ErrorRate: v}, {HeldoutShare: v}} {
			_, err := (&Gateway{}).SeedSyntheticClass(context.Background(), connect.NewRequest(req))
			if connect.CodeOf(err) != connect.CodeInvalidArgument {
				t.Fatalf("got %v", err)
			}
		}
	}
}
