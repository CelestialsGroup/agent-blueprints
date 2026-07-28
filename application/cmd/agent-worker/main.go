package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.temporal.io/sdk/client"

	"github.com/shell-echo/agent/internal/orchestration/temporaladapter"
	"github.com/shell-echo/agent/internal/persistence"
)

type processConfig struct {
	databaseDSN string
	temporal    temporaladapter.Config
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	if err := run(ctx, os.LookupEnv); err != nil {
		slog.Error("agent worker stopped", "error", err)
		os.Exit(1)
	}
}

func run(
	ctx context.Context,
	lookupEnv func(string) (string, bool),
) error {
	config, err := loadConfig(lookupEnv)
	if err != nil {
		return err
	}

	poolConfig, err := pgxpool.ParseConfig(config.databaseDSN)
	if err != nil {
		return errors.New("parse PostgreSQL configuration")
	}
	poolConfig.MaxConns = 8
	pool, err := pgxpool.NewWithConfig(ctx, poolConfig)
	if err != nil {
		return fmt.Errorf("open PostgreSQL pool: %w", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		return fmt.Errorf("ping PostgreSQL: %w", err)
	}

	runner, err := persistence.NewTransactionRunner(pool)
	if err != nil {
		return err
	}
	workflowRuns, err := persistence.NewWorkflowRunRepository(runner)
	if err != nil {
		return err
	}
	activities, err := temporaladapter.NewActivities(workflowRuns)
	if err != nil {
		return err
	}
	temporalClient, err := client.DialContext(ctx, client.Options{
		HostPort:  config.temporal.Address,
		Namespace: config.temporal.Namespace,
	})
	if err != nil {
		return fmt.Errorf("dial Temporal: %w", err)
	}
	defer temporalClient.Close()
	temporalWorker, err := temporaladapter.NewWorker(temporalClient, config.temporal, activities)
	if err != nil {
		return err
	}
	return temporaladapter.RunWorker(ctx, temporalWorker)
}

func loadConfig(lookupEnv func(string) (string, bool)) (processConfig, error) {
	if lookupEnv == nil {
		return processConfig{}, errors.New("environment lookup is required")
	}
	require := func(name string) (string, error) {
		value, ok := lookupEnv(name)
		if !ok || value == "" {
			return "", fmt.Errorf("%s is required", name)
		}
		if len(value) > 4096 || strings.IndexByte(value, 0) >= 0 {
			return "", fmt.Errorf("%s is invalid", name)
		}
		return value, nil
	}
	databaseDSN, err := require("AGENT_DATABASE_DSN")
	if err != nil {
		return processConfig{}, err
	}
	temporalConfig := temporaladapter.DefaultConfig()
	values := []struct {
		name   string
		target *string
	}{
		{"AGENT_TEMPORAL_ADDRESS", &temporalConfig.Address},
		{"AGENT_TEMPORAL_NAMESPACE", &temporalConfig.Namespace},
		{"AGENT_TEMPORAL_TASK_QUEUE", &temporalConfig.TaskQueue},
		{"AGENT_TEMPORAL_ENGINE_VERSION", &temporalConfig.EngineVersion},
		{"AGENT_WORKER_DEPLOYMENT", &temporalConfig.WorkerDeployment},
		{"AGENT_WORKER_BUILD_ID", &temporalConfig.WorkerBuildID},
	}
	for _, item := range values {
		value, err := require(item.name)
		if err != nil {
			return processConfig{}, err
		}
		*item.target = value
	}
	if err := temporalConfig.Validate(); err != nil {
		return processConfig{}, err
	}
	return processConfig{databaseDSN: databaseDSN, temporal: temporalConfig}, nil
}
