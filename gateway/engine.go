package main

import (
	"context"
	"crypto/tls"
	"net"
	"net/http"
	"strings"

	"connectrpc.com/connect"
	"golang.org/x/net/http2"

	"misconception/gen/go/misconception/v1/misconceptionv1connect"
)

// newEngineClient returns a connect-go client that speaks gRPC to the Python
// engine over cleartext HTTP/2 (h2c), per spec section 6.2.
func newEngineClient(addr string) misconceptionv1connect.EngineServiceClient {
	return misconceptionv1connect.NewEngineServiceClient(h2cClient(), normalizeAddr(addr), connect.WithGRPC())
}

func newAgentClient(addr string) misconceptionv1connect.InstructorAgentServiceClient {
	return misconceptionv1connect.NewInstructorAgentServiceClient(h2cClient(), normalizeAddr(addr), connect.WithGRPC())
}

func h2cClient() *http.Client {
	return &http.Client{Transport: &http2.Transport{
		AllowHTTP: true,
		DialTLSContext: func(ctx context.Context, network, addr string, _ *tls.Config) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, network, addr)
		},
	}}
}

func normalizeAddr(addr string) string {
	if !strings.HasPrefix(addr, "http://") && !strings.HasPrefix(addr, "https://") {
		return "http://" + addr
	}
	return strings.TrimRight(addr, "/")
}
