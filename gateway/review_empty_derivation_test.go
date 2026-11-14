package main

import (
	"connectrpc.com/connect"
	"context"
	v1 "misconception/gen/go/misconception/v1"
	"testing"
)

func TestEmptyDerivation(t *testing.T) {
	_, err := (&Gateway{}).TryDerivation(context.Background(), connect.NewRequest(&v1.TryDerivationRequest{}))
	if connect.CodeOf(err) != connect.CodeInvalidArgument {
		t.Fatalf("got %v", err)
	}
}
