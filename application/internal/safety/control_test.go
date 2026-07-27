package safety

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/shell-echo/agent/internal/domain/tenancy"
)

func TestLockedContractDigestVectors(t *testing.T) {
	t.Parallel()

	safetyControl := SystemSafetyControl{
		SafetyControlID:    "ssc_01J00000000000000000000000",
		TenantID:           "ten_01J00000000000000000000000",
		WorkOrderID:        "wrk_01J00000000000000000000000",
		RuntimeRunID:       "rtr_01J00000000000000000000000",
		Action:             ActionCancel,
		Reason:             ReasonCommercialAuthorizationExpired,
		EvidenceContractID: "urn:agent-platform:runtime-authorization:v1",
		EvidenceID:         "rauth_01J000000000000000000000",
		EvidenceDigest:     "sha256:293ba3d16c08559c497d4ac197a774e5669e71537fc8ea8e2f6f211b9d10ceb7",
		ObservedAt:         mustTime(t, "2026-07-16T09:15:01Z"),
		IssuerSubjectID:    "spn_agent_safety_controller",
		IssuedAt:           mustTime(t, "2026-07-16T09:16:00Z"),
		ControlDigest:      "sha256:3a8b5550fb8068cbf794b3adbd8edb6c76b280bd5fc382c329ad924b72393c0e",
	}
	if err := safetyControl.Validate(safetyControl.TenantID); err != nil {
		t.Fatalf("locked SystemSafetyControl digest: %v", err)
	}

	command := RuntimeCommand{
		CommandID:                  "rtcmd_01J0000000000000000000000",
		CommandDigest:              "sha256:76158e91ff25543855b9b34a5b1b31b05ae8633b6ff93abcb658cf17689ee278",
		WorkOrderID:                "wrk_01J00000000000000000000000",
		RuntimeRunID:               "rtr_01J00000000000000000000000",
		CommandSequence:            2,
		Type:                       ActionAppendInput,
		AuthorizedControlRequestID: "ctl_01J00000000000000000000000",
		InputID:                    "rin_01J00000000000000000000001",
		InputContentDigest:         "sha256:3ee5da709dc141b215e943a10388da878f35902be68783b0fc7fbe4b5ebee529",
		InvocationID:               "inv_runtime_command_01J0000000000000",
		InvocationAttemptID:        "iat_runtime_01J0000000000000001",
		FencingToken:               2,
		IdempotencyKey:             "runtime-command-key-0002",
		DeadlineAt:                 mustTime(t, "2026-07-16T09:14:00Z"),
		CreatedAt:                  mustTime(t, "2026-07-16T09:13:00Z"),
	}
	if err := command.Validate(); err != nil {
		t.Fatalf("locked AgentRuntimeCommand digest: %v", err)
	}
	tooLong := command
	tooLong.CommandID = strings.Repeat("x", maxIdentifierRunes+1)
	if err := tooLong.Validate(); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("unbounded Contract command ID = %v, want fail-closed Application bound", err)
	}
	nulIdentifier := command
	nulIdentifier.InvocationID = "invocation\x00identifier"
	if err := nulIdentifier.Validate(); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("PostgreSQL-unrepresentable command ID = %v, want fail-closed", err)
	}
	invalidOptionalIdentifier := command
	invalidOptionalIdentifier.AuthorizedControlRequestID = "control\x00request"
	if err := invalidOptionalIdentifier.Validate(); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("PostgreSQL-unrepresentable optional authority ID = %v, want fail-closed", err)
	}
	invalidReasonUTF8 := command
	invalidReasonUTF8.Reason = string([]byte{0xff})
	if err := invalidReasonUTF8.Validate(); !errors.Is(err, ErrInvalidControl) {
		t.Fatalf("invalid UTF-8 command reason = %v, want fail-closed", err)
	}
	invalidApprovalUTF8 := command
	invalidApprovalUTF8.Type = ActionApprovalDecision
	invalidApprovalUTF8.InputID = ""
	invalidApprovalUTF8.InputContentDigest = ""
	invalidApprovalUTF8.Approval = &Approval{
		ApprovalID: "approval",
		Decision:   "approve",
		Comment:    string([]byte{0xff}),
	}
	if err := invalidApprovalUTF8.Validate(); !errors.Is(err, ErrInvalidControl) {
		t.Fatalf("invalid UTF-8 approval comment = %v, want fail-closed", err)
	}
	subMicrosecondDeadline := command
	subMicrosecondDeadline.DeadlineAt = subMicrosecondDeadline.CreatedAt.Add(time.Nanosecond)
	if err := subMicrosecondDeadline.Validate(); !errors.Is(err, ErrInvalidControl) {
		t.Fatalf("sub-microsecond command deadline = %v, want fail-closed", err)
	}

	fanout := FanoutSnapshot{
		FanoutID:        "fan_01J00000000000000000000000",
		FanoutVersion:   1,
		FanoutDigest:    "sha256:ec20be4e32dd13ec6e9daa1645dd456b43bfd900b0c22f9404f3cd21b404828d",
		TenantID:        "ten_01J00000000000000000000000",
		WorkOrderID:     "wrk_01J00000000000000000000000",
		Action:          ActionCancel,
		AuthorityKind:   FanoutUserAuthority,
		AuthorityID:     "ctl_cancel_01J0000000000000000000",
		AuthorityDigest: "sha256:2bc67f169c1fa4957c92af914d709c9d236556b414e999c1a0079d634d604fac",
		Targets: []FanoutTarget{
			{
				AgentRunID:         "agr_01J00000000000000000000000",
				RuntimeRunID:       "rtr_01J00000000000000000000000",
				TargetFencingToken: 3,
				CommandID:          "internal-command-root",
				ControlState:       ControlPending,
			},
			{
				AgentRunID:         "agr_child_01J0000000000000000000",
				RuntimeRunID:       "rtr_child_01J0000000000000000000",
				TargetFencingToken: 2,
				CommandID:          "internal-command-child",
				ControlState:       ControlPending,
			},
		},
		CreatedAt: mustTime(t, "2026-07-16T09:03:00Z"),
		UpdatedAt: mustTime(t, "2026-07-16T09:03:00Z"),
	}
	if err := fanout.Validate(fanout.TenantID); err != nil {
		t.Fatalf("locked AgentRunControlFanout digest: %v", err)
	}
}

func TestControlAuthorityAndProgressFailClosed(t *testing.T) {
	t.Parallel()
	tenantID := tenancy.TenantID("tenant-a")
	decision := ChildAdmissionAuthority{
		TenantID:           tenantID,
		WorkOrderID:        "work-order",
		DecisionID:         "decision",
		DecisionDigest:     testDigest("1"),
		SpawnRequestID:     "spawn-request",
		SpawnRequestDigest: testDigest("2"),
		ParentAgentRunID:   "parent-run",
		Outcome:            AdmissionAccepted,
		ReasonCodes:        []string{"policy_denied"},
		ChildAgentRunID:    "child-run",
		RuntimeRunID:       "runtime-run",
		DecidedAt:          mustTime(t, "2026-07-27T00:00:00Z"),
	}
	if err := decision.Validate(tenantID); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("accepted admission with non-admitted reason = %v", err)
	}

	if CanProgress(ControlConfirmed, ControlDispatched) {
		t.Fatal("confirmed fanout target regressed to dispatched")
	}
	if !CanProgress(ControlOutcomeUnknown, ControlConfirmed) {
		t.Fatal("outcome_unknown did not reconcile to confirmed")
	}

	control := SystemSafetyControl{
		SafetyControlID: "control", TenantID: tenantID, WorkOrderID: "work-order",
		RuntimeRunID: "runtime-run", Action: ActionResume,
		Reason:             ReasonOperatorEmergencyStop,
		EvidenceContractID: "urn:agent-platform:safety-evidence:v1",
		EvidenceID:         "evidence", EvidenceDigest: testDigest("3"),
		ObservedAt:      mustTime(t, "2026-07-27T00:00:00Z"),
		IssuerSubjectID: "controller", IssuedAt: mustTime(t, "2026-07-27T00:01:00Z"),
	}
	if err := control.Validate(tenantID); !errors.Is(err, ErrInvalidControl) {
		t.Fatalf("system resume control = %v, want invalid control", err)
	}
	policyPause := control
	policyPause.Action = ActionPause
	policyPause.Reason = ReasonPolicyRevoked
	if err := policyPause.Validate(tenantID); !errors.Is(err, ErrInvalidControl) {
		t.Fatalf("policy-revocation pause control = %v, want invalid control", err)
	}

	command := RuntimeCommand{
		CommandID: "command", WorkOrderID: "work-order", RuntimeRunID: "runtime-run",
		CommandSequence: 1, Type: ActionCancel,
		AuthorizedControlRequestID: "request", SystemSafetyControlID: "control",
		SystemSafetyControlDigest: testDigest("4"), InvocationID: "invocation",
		InvocationAttemptID: "attempt", FencingToken: 1,
		IdempotencyKey: "mixed-authority-command", DeadlineAt: mustTime(t, "2026-07-27T00:02:00Z"),
		CreatedAt: mustTime(t, "2026-07-27T00:01:00Z"),
	}
	if err := command.Validate(); !errors.Is(err, ErrInvalidControl) {
		t.Fatalf("mixed command authority = %v, want invalid control", err)
	}

	approvalRequest := ControlRequestAuthority{
		TenantID: tenantID, WorkOrderID: "work-order", ControlRequestID: "approval-request",
		RequestDigest: testDigest("5"), Action: ActionApprovalDecision,
		ExpectedActiveWorkVersion: 1,
		Approval: &Approval{
			ApprovalID: "approval", Decision: "approve", Comment: string([]byte{0xff}),
		},
		AcceptedAt: mustTime(t, "2026-07-27T00:01:00Z"),
	}
	if err := approvalRequest.Validate(tenantID); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("invalid UTF-8 control-request approval comment = %v, want fail-closed", err)
	}
}

func mustTime(t *testing.T, value string) time.Time {
	t.Helper()
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		t.Fatalf("parse time %q: %v", value, err)
	}
	return parsed
}

func testDigest(nibble string) string {
	return "sha256:" + nibble + "000000000000000000000000000000000000000000000000000000000000000"
}
