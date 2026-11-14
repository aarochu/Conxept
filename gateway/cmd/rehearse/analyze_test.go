package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"connectrpc.com/connect"
	v1 "misconception/gen/go/misconception/v1"
	"misconception/gen/go/misconception/v1/misconceptionv1connect"
)

type scriptedAnalyze struct {
	misconceptionv1connect.UnimplementedGatewayServiceHandler
	tools bool
}

func (g *scriptedAnalyze) AnalyzeClass(ctx context.Context, req *connect.Request[v1.AnalyzeClassRequest], stream *connect.ServerStream[v1.AnalyzeClassResponse]) error {
	if g.tools {
		if err := stream.Send(&v1.AnalyzeClassResponse{Event: &v1.AnalyzeResponse{Event: &v1.AnalyzeResponse_ToolCall{ToolCall: &v1.ToolCallEvent{Name: "get_clusters"}}}}); err != nil {
			return err
		}
	}
	return stream.Send(&v1.AnalyzeClassResponse{Event: &v1.AnalyzeResponse{Event: &v1.AnalyzeResponse_Brief{Brief: &v1.BriefEvent{BriefId: "example", Markdown: "Brief"}}}})
}

func TestRequireAnalyze(t *testing.T) {
	for _, tools := range []bool{false, true} {
		_, handler := misconceptionv1connect.NewGatewayServiceHandler(&scriptedAnalyze{tools: tools})
		server := httptest.NewServer(handler)
		client := misconceptionv1connect.NewGatewayServiceClient(http.DefaultClient, server.URL)
		for _, strict := range []bool{false, true} {
			for _, st := range demoSteps(strict) {
				if st.name != "analyze class (model)" {
					continue
				}
				if st.optional == strict {
					t.Fatal("Analyze optional flag does not match rehearsal mode")
				}
				_, err := st.run(context.Background(), &state{c: client, classID: "example"})
				if (err != nil) != (strict && !tools) {
					t.Errorf("strict=%v tools=%v: %v", strict, tools, err)
				}
			}
		}
		server.Close()
	}
}
