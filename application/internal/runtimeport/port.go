package runtimeport

import "context"

// AgentRuntimeProvider is a framework-neutral Port. Implementations must perform
// exactly one dispatch for Start and Command; retry belongs to the durable caller.
type AgentRuntimeProvider interface {
	Capabilities(context.Context, CapabilitiesRequest) ReadResult[ProviderCapabilities]
	Start(context.Context, StartRequest) MutationOutcome
	Status(context.Context, StatusRequest) ReadResult[RunStatus]
	Command(context.Context, CommandRequest) MutationOutcome
	Events(context.Context, EventsRequest) ReadResult[EventPage]
}
