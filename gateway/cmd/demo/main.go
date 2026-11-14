// Command demo seeds the default synthetic class and processes it through the
// gateway, printing progress and the evaluation (spec section 9, `make demo`).
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"time"

	"connectrpc.com/connect"

	v1 "misconception/gen/go/misconception/v1"
	"misconception/gen/go/misconception/v1/misconceptionv1connect"
)

func main() {
	url := flag.String("gateway", "http://localhost:8080", "gateway base URL")
	students := flag.Int("students", 60, "number of synthetic students")
	seed := flag.Int64("seed", 7, "class seed")
	flag.Parse()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	c := misconceptionv1connect.NewGatewayServiceClient(http.DefaultClient, *url)

	start := time.Now()
	seeded, err := c.SeedSyntheticClass(ctx, connect.NewRequest(&v1.SeedSyntheticClassRequest{
		NumStudents: int32(*students), Seed: *seed,
	}))
	if err != nil {
		log.Fatalf("seed: %v", err)
	}
	info := seeded.Msg.ClassInfo
	fmt.Printf("seeded %q: %d submissions (class %s)\n", info.Name, info.NumSubmissions, info.Id)

	stream, err := c.ProcessClass(ctx, connect.NewRequest(&v1.ProcessClassRequest{ClassId: info.Id}))
	if err != nil {
		log.Fatalf("process: %v", err)
	}
	for stream.Receive() {
		m := stream.Msg()
		if m.Done == m.Total || m.Done%50 == 0 {
			fmt.Printf("\rprocessed %d / %d", m.Done, m.Total)
		}
	}
	if err := stream.Err(); err != nil {
		log.Fatalf("\nprocess: %v", err)
	}
	fmt.Printf("\nseed + process: %s\n", time.Since(start).Round(time.Millisecond))

	ev, err := c.GetEvaluation(ctx, connect.NewRequest(&v1.GetEvaluationRequest{ClassId: info.Id}))
	if err != nil {
		log.Fatalf("evaluation: %v", err)
	}
	e := ev.Msg
	fmt.Printf("false alarms %d of %d correct | step %d/%d | label %d/%d | held-out %d/%d\n",
		e.FalseAlarms, e.CorrectSubmissions, e.DivergenceStepCorrect, e.DivergenceStepExpected,
		e.LabelCorrect, e.LabelExpected, e.HeldoutDetected, e.HeldoutExpected)
	fmt.Printf("dashboard: %s/class/%s\n", *url, info.Id)
}
