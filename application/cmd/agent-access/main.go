package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/shell-echo/agent-application-platform/internal/agentaccess"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	config := agentaccess.DefaultConfig()
	if address := os.Getenv("AGENT_ACCESS_ADDRESS"); address != "" {
		config.Address = address
	}

	if err := agentaccess.Run(ctx, config); err != nil {
		slog.Error("agent access stopped", "error", err)
		os.Exit(1)
	}
}
