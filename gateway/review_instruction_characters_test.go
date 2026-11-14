package main

import (
	"strings"
	"testing"
)

func TestUnicodeInstructionLimit(t *testing.T) {
	if instructionTooLong(strings.Repeat("界", 500)) {
		t.Fatal("500 characters rejected")
	}
	if !instructionTooLong(strings.Repeat("界", 501)) {
		t.Fatal("501 characters accepted")
	}
}
