package agentaccess

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
)

const maxHeaderBytes = 32 << 10

type Config struct {
	Address         string
	ShutdownTimeout time.Duration
}

func DefaultConfig() Config {
	return Config{
		Address:         ":8080",
		ShutdownTimeout: 15 * time.Second,
	}
}

func (config Config) validate() error {
	if config.Address == "" {
		return errors.New("address is required")
	}
	if config.ShutdownTimeout <= 0 {
		return errors.New("shutdown timeout must be positive")
	}
	return nil
}

func NewHandler() http.Handler {
	router := chi.NewRouter()
	router.Get("/health/startup", healthHandler)
	router.Get("/health/ready", healthHandler)
	router.Get("/health/live", healthHandler)
	return router
}

func Run(ctx context.Context, config Config) error {
	if err := config.validate(); err != nil {
		return fmt.Errorf("validate agent access config: %w", err)
	}

	listener, err := net.Listen("tcp", config.Address)
	if err != nil {
		return fmt.Errorf("listen on %s: %w", config.Address, err)
	}

	server := &http.Server{
		Handler:           NewHandler(),
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    maxHeaderBytes,
	}

	serveErrors := make(chan error, 1)
	go func() {
		serveErrors <- server.Serve(listener)
	}()

	select {
	case err := <-serveErrors:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return fmt.Errorf("serve agent access: %w", err)
	case <-ctx.Done():
		shutdownContext, cancel := context.WithTimeout(context.Background(), config.ShutdownTimeout)
		defer cancel()
		if err := server.Shutdown(shutdownContext); err != nil {
			return fmt.Errorf("shutdown agent access: %w", err)
		}
		return nil
	}
}

func healthHandler(response http.ResponseWriter, _ *http.Request) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(response).Encode(map[string]string{"status": "ok"})
}
