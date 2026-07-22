package agentaccess

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHealthEndpoints(t *testing.T) {
	t.Parallel()

	for _, path := range []string{"/health/startup", "/health/ready", "/health/live"} {
		path := path
		t.Run(path, func(t *testing.T) {
			t.Parallel()
			request := httptest.NewRequest(http.MethodGet, path, nil)
			response := httptest.NewRecorder()

			NewHandler().ServeHTTP(response, request)

			if response.Code != http.StatusOK {
				t.Fatalf("status = %d, want %d", response.Code, http.StatusOK)
			}
			if contentType := response.Header().Get("Content-Type"); contentType != "application/json" {
				t.Fatalf("content type = %q, want application/json", contentType)
			}
			if body := response.Body.String(); body != "{\"status\":\"ok\"}\n" {
				t.Fatalf("body = %q, want health response", body)
			}
		})
	}
}

func TestUnknownRouteIsNotFound(t *testing.T) {
	t.Parallel()

	request := httptest.NewRequest(http.MethodGet, "/v1/work-orders", nil)
	response := httptest.NewRecorder()

	NewHandler().ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusNotFound)
	}
}

func TestRunRejectsInvalidConfiguration(t *testing.T) {
	t.Parallel()

	err := Run(context.Background(), Config{})
	if err == nil {
		t.Fatal("Run() error = nil, want invalid configuration error")
	}
}
