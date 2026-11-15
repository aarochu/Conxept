// Command snapshot captures one processed class from a running gateway into snapshot.json, which the
// web app replays in the browser when deployed without a backend (web/src/app/snapshot.ts).
//
//	go run ./cmd/snapshot -gateway http://localhost:8081 -out ../web/dist/web/browser/snapshot.json
//
// It reads only: the class list, heatmap, clusters, evaluation, every cluster's example submissions,
// three practice problems per catalog misconception, and one live Analyze run (which must end in a
// brief that passed the number check).
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"net/http"
	"os"
	"time"

	"connectrpc.com/connect"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"

	v1 "misconception/gen/go/misconception/v1"
	"misconception/gen/go/misconception/v1/misconceptionv1connect"
)

type snapshot struct {
	CapturedAt         string                     `json:"capturedAt"`
	ListProblems       json.RawMessage            `json:"listProblems"`
	ListMisconceptions json.RawMessage            `json:"listMisconceptions"`
	ListClasses        json.RawMessage            `json:"listClasses"`
	Heatmap            json.RawMessage            `json:"heatmap"`
	Clusters           json.RawMessage            `json:"clusters"`
	Evaluation         json.RawMessage            `json:"evaluation"`
	Submissions        map[string]json.RawMessage `json:"submissions"`
	Remediation        map[string]json.RawMessage `json:"remediation"`
	Analyze            []json.RawMessage          `json:"analyze"`
}

func main() {
	gateway := flag.String("gateway", "http://localhost:8081", "gateway base URL")
	out := flag.String("out", "snapshot.json", "output file")
	allowNoBrief := flag.Bool("allow-missing-analyze", false, "write the snapshot even if no live Analyze run succeeds (the replay then shows no brief)")
	flag.Parse()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	if err := capture(ctx, misconceptionv1connect.NewGatewayServiceClient(http.DefaultClient, *gateway), *out, *allowNoBrief); err != nil {
		fmt.Fprintf(os.Stderr, "FAILED: %v\n", err)
		os.Exit(1)
	}
}

func js(m proto.Message) json.RawMessage {
	b, err := protojson.Marshal(m)
	if err != nil {
		panic(err)
	}
	return b
}

func capture(ctx context.Context, c misconceptionv1connect.GatewayServiceClient, out string, allowNoBrief bool) error {
	s := snapshot{CapturedAt: time.Now().UTC().Format(time.RFC3339), Submissions: map[string]json.RawMessage{}, Remediation: map[string]json.RawMessage{}}

	classes, err := c.ListClasses(ctx, connect.NewRequest(&v1.ListClassesRequest{}))
	if err != nil {
		return fmt.Errorf("list classes: %w", err)
	}
	var class *v1.ClassInfo
	for _, ci := range classes.Msg.Classes {
		if ci.Processed {
			class = ci
		}
	}
	if class == nil {
		return errors.New("no processed class: seed and process one first")
	}
	s.ListClasses = js(&v1.ListClassesResponse{Classes: []*v1.ClassInfo{class}})
	id := class.Id

	problems, err := c.ListProblems(ctx, connect.NewRequest(&v1.GatewayServiceListProblemsRequest{}))
	if err != nil {
		return fmt.Errorf("list problems: %w", err)
	}
	s.ListProblems = js(problems.Msg)
	catalog, err := c.ListMisconceptions(ctx, connect.NewRequest(&v1.GatewayServiceListMisconceptionsRequest{}))
	if err != nil {
		return fmt.Errorf("list misconceptions: %w", err)
	}
	s.ListMisconceptions = js(catalog.Msg)

	heat, err := c.GetHeatmap(ctx, connect.NewRequest(&v1.GetHeatmapRequest{ClassId: id}))
	if err != nil {
		return fmt.Errorf("heatmap: %w", err)
	}
	s.Heatmap = js(heat.Msg)
	clusters, err := c.GetClusters(ctx, connect.NewRequest(&v1.GetClustersRequest{ClassId: id}))
	if err != nil {
		return fmt.Errorf("clusters: %w", err)
	}
	s.Clusters = js(clusters.Msg)
	eval, err := c.GetEvaluation(ctx, connect.NewRequest(&v1.GetEvaluationRequest{ClassId: id}))
	if err != nil {
		return fmt.Errorf("evaluation: %w", err)
	}
	s.Evaluation = js(eval.Msg)

	for _, cl := range clusters.Msg.Clusters {
		for _, sid := range cl.ExampleSubmissionIds {
			if _, done := s.Submissions[sid]; done {
				continue
			}
			sub, err := c.GetSubmission(ctx, connect.NewRequest(&v1.GetSubmissionRequest{SubmissionId: sid}))
			if err != nil {
				return fmt.Errorf("submission %s: %w", sid, err)
			}
			s.Submissions[sid] = js(sub.Msg)
		}
	}
	fmt.Printf("class %s: %d example submissions\n", id, len(s.Submissions))

	for _, m := range catalog.Msg.Misconceptions {
		rem, err := c.GenerateRemediation(ctx, connect.NewRequest(&v1.GatewayServiceGenerateRemediationRequest{MisconceptionId: m.Id, Count: 3}))
		if err != nil {
			return fmt.Errorf("practice for %s: %w", m.Id, err)
		}
		s.Remediation[m.Id] = js(rem.Msg)
	}
	fmt.Printf("practice for %d misconceptions\n", len(s.Remediation))

	for attempt := 1; attempt <= 3; attempt++ {
		events, err := analyze(ctx, c, id)
		if err == nil {
			s.Analyze = events
			fmt.Printf("analyze: %d events ending in a brief (attempt %d)\n", len(events), attempt)
			break
		}
		fmt.Printf("analyze attempt %d: %v\n", attempt, err)
		if attempt == 3 {
			if !allowNoBrief {
				return fmt.Errorf("analyze: %w", err)
			}
			s.Analyze = []json.RawMessage{}
		}
	}

	b, err := json.Marshal(s)
	if err != nil {
		return err
	}
	if err := os.WriteFile(out, b, 0o644); err != nil {
		return err
	}
	fmt.Printf("wrote %s (%d KB)\n", out, len(b)/1024)
	return nil
}

func analyze(ctx context.Context, c misconceptionv1connect.GatewayServiceClient, id string) ([]json.RawMessage, error) {
	stream, err := c.AnalyzeClass(ctx, connect.NewRequest(&v1.AnalyzeClassRequest{ClassId: id}))
	if err != nil {
		return nil, err
	}
	defer stream.Close()
	var events []json.RawMessage
	for stream.Receive() {
		ev := stream.Msg()
		if msg := ev.GetEvent().GetError(); msg != "" {
			return nil, errors.New(msg)
		}
		events = append(events, js(ev))
		if ev.GetEvent().GetBrief() != nil {
			return events, nil
		}
	}
	if err := stream.Err(); err != nil {
		return nil, err
	}
	return nil, errors.New("stream ended without a brief")
}
