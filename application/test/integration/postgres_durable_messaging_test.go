//go:build integration

package integration_test

import (
	"context"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/messaging"
	"github.com/shell-echo/agent/internal/persistence"
)

func TestPostgreSQLDurableMessagingAtomicityRecoveryAndIsolation(t *testing.T) {
	ctx := context.Background()
	adminDSN := requiredEnv(t, "AGENT_TEST_ADMIN_DSN")
	adminPool := openPool(t, adminDSN, 4)
	createDatabase(t, ctx, adminPool, agentDatabase)
	t.Cleanup(func() { dropDatabase(t, adminPool, agentDatabase) })

	databaseAdminDSN := replaceDatabase(t, adminDSN, agentDatabase, "postgres", "b021-integration-admin")
	runGoose(t, databaseAdminDSN, "up", true)
	assertMigrationVersion(t, databaseAdminDSN, 3)
	databaseAdminPool := openPool(t, databaseAdminDSN, 4)
	createApplicationLogin(t, ctx, databaseAdminPool)

	applicationDSN := replaceDatabase(t, adminDSN, agentDatabase, applicationLogin, applicationPass)
	applicationPool := openPool(t, applicationDSN, 12)
	runner, err := persistence.NewTransactionRunner(applicationPool)
	if err != nil {
		t.Fatalf("create transaction runner: %v", err)
	}
	clientRepository, err := persistence.NewClientApplicationRepository(runner)
	if err != nil {
		t.Fatalf("create client application repository: %v", err)
	}
	outbox, err := persistence.NewOutboxRepository(runner)
	if err != nil {
		t.Fatalf("create outbox repository: %v", err)
	}
	inbox, err := persistence.NewInboxConsumer(runner)
	if err != nil {
		t.Fatalf("create inbox consumer: %v", err)
	}

	baseTime := time.Date(2026, time.July, 23, 3, 0, 0, 0, time.UTC)
	deferredTime := baseTime.AddDate(100, 0, 0)
	tenantA := tenancy.Tenant{ID: "tenant-a", DisplayName: "Tenant A", CreatedAt: baseTime}
	tenantB := tenancy.Tenant{ID: "tenant-b", DisplayName: "Tenant B", CreatedAt: baseTime}
	registerClient(t, ctx, clientRepository, tenantA, "client-a", baseTime)
	registerClient(t, ctx, clientRepository, tenantB, "client-b", baseTime)

	t.Run("domain change and Outbox commit or rollback together", func(t *testing.T) {
		commitClient := tenancy.ClientApplication{
			TenantID: tenantA.ID, ID: "client-atomic-commit", DisplayName: "Atomic Commit", CreatedAt: baseTime,
		}
		commitMessage := mustOutbound(
			t,
			"outbox-atomic-commit",
			[]byte(`{"kind":"commit"}`),
			deferredTime,
			baseTime,
		)
		if err := runner.Run(ctx, tenantA.ID, func(
			ctx context.Context,
			repository persistence.TenantRepository,
		) error {
			if _, err := repository.RegisterClientApplication(ctx, tenantA, commitClient); err != nil {
				return err
			}
			outcome, err := repository.EnqueueOutboxMessage(ctx, commitMessage)
			if err != nil {
				return err
			}
			if outcome != messaging.EnqueueInserted {
				t.Fatalf("committed Outbox outcome = %s, want inserted", outcome)
			}
			return nil
		}); err != nil {
			t.Fatalf("commit domain change and Outbox: %v", err)
		}
		if _, err := clientRepository.Find(ctx, tenantA.ID, commitClient.ID); err != nil {
			t.Fatalf("committed domain change is missing: %v", err)
		}
		if status, err := outbox.Status(ctx, tenantA.ID, commitMessage.MessageID); err != nil || status.State != messaging.OutboxPending {
			t.Fatalf("committed Outbox status = %#v, %v", status, err)
		}

		rollbackClient := tenancy.ClientApplication{
			TenantID: tenantA.ID, ID: "client-atomic-rollback", DisplayName: "Atomic Rollback", CreatedAt: baseTime,
		}
		rollbackMessage := mustOutbound(
			t,
			"outbox-atomic-rollback",
			[]byte(`{"kind":"rollback"}`),
			deferredTime,
			baseTime,
		)
		rollbackMarker := errors.New("force durable messaging rollback")
		err = runner.Run(ctx, tenantA.ID, func(
			ctx context.Context,
			repository persistence.TenantRepository,
		) error {
			if _, err := repository.RegisterClientApplication(ctx, tenantA, rollbackClient); err != nil {
				return err
			}
			if _, err := repository.EnqueueOutboxMessage(ctx, rollbackMessage); err != nil {
				return err
			}
			return rollbackMarker
		})
		if !errors.Is(err, rollbackMarker) {
			t.Fatalf("rollback transaction = %v, want marker", err)
		}
		if _, err := clientRepository.Find(ctx, tenantA.ID, rollbackClient.ID); !errors.Is(err, persistence.ErrNotFound) {
			t.Fatalf("rolled-back domain change = %v, want not found", err)
		}
		if _, err := outbox.Status(ctx, tenantA.ID, rollbackMessage.MessageID); !errors.Is(err, messaging.ErrMessagingNotFound) {
			t.Fatalf("rolled-back Outbox = %v, want not found", err)
		}

		if err := runner.Run(ctx, tenantA.ID, func(
			ctx context.Context,
			repository persistence.TenantRepository,
		) error {
			outcome, err := repository.EnqueueOutboxMessage(ctx, commitMessage)
			if err != nil {
				return err
			}
			if outcome != messaging.EnqueueReplay {
				t.Fatalf("identical Outbox replay = %s, want replay", outcome)
			}
			return nil
		}); err != nil {
			t.Fatalf("replay identical Outbox: %v", err)
		}
		createdAtConflict := mustOutbound(
			t,
			commitMessage.MessageID,
			commitMessage.Payload,
			commitMessage.AvailableAt,
			baseTime.Add(time.Second),
		)
		err := runner.Run(ctx, tenantA.ID, func(
			ctx context.Context,
			repository persistence.TenantRepository,
		) error {
			_, err := repository.EnqueueOutboxMessage(ctx, createdAtConflict)
			return err
		})
		if !errors.Is(err, messaging.ErrOutboxConflict) {
			t.Fatalf("Outbox replay with changed created_at = %v, want ErrOutboxConflict", err)
		}
		conflictingMessage := mustOutbound(
			t,
			commitMessage.MessageID,
			[]byte(`{"kind":"different"}`),
			commitMessage.AvailableAt,
			baseTime,
		)
		err = runner.Run(ctx, tenantA.ID, func(
			ctx context.Context,
			repository persistence.TenantRepository,
		) error {
			_, err := repository.EnqueueOutboxMessage(ctx, conflictingMessage)
			return err
		})
		if !errors.Is(err, messaging.ErrOutboxConflict) {
			t.Fatalf("conflicting Outbox replay = %v, want ErrOutboxConflict", err)
		}
	})

	t.Run("Transport message identity is global before dispatch", func(t *testing.T) {
		messageA := mustOutbound(
			t,
			"outbox-global-transport-identity",
			[]byte(`{"tenant":"a"}`),
			deferredTime,
			baseTime,
		)
		enqueue(t, ctx, runner, tenantA.ID, messageA)

		messageB := mustOutbound(
			t,
			messageA.MessageID,
			[]byte(`{"tenant":"b"}`),
			messageA.AvailableAt,
			baseTime,
		)
		err := runner.Run(ctx, tenantB.ID, func(
			ctx context.Context,
			repository persistence.TenantRepository,
		) error {
			_, err := repository.EnqueueOutboxMessage(ctx, messageB)
			return err
		})
		if !errors.Is(err, messaging.ErrOutboxConflict) {
			t.Fatalf("cross-Tenant Transport Message ID reuse = %v, want ErrOutboxConflict", err)
		}
		if err.Error() != messaging.ErrOutboxConflict.Error() {
			t.Fatalf("cross-Tenant Transport Message ID conflict leaked details: %v", err)
		}
		if _, err := outbox.Status(ctx, tenantB.ID, messageB.MessageID); !errors.Is(err, messaging.ErrMessagingNotFound) {
			t.Fatalf("cross-Tenant Transport Message ID conflict leaked a row = %v, want not found", err)
		}
		if status, err := outbox.Status(ctx, tenantA.ID, messageA.MessageID); err != nil || status.State != messaging.OutboxPending {
			t.Fatalf("original Transport message after conflict = %#v, %v", status, err)
		}
	})

	t.Run("Outbox status preserves Unicode identifier semantics", func(t *testing.T) {
		messageID := strings.Repeat("界", 200)
		message := mustOutbound(
			t,
			messageID,
			[]byte(`{"kind":"unicode"}`),
			deferredTime,
			baseTime,
		)
		enqueue(t, ctx, runner, tenantA.ID, message)
		status, err := outbox.Status(ctx, tenantA.ID, messageID)
		if err != nil || status.MessageID != messageID {
			t.Fatalf("read Unicode Outbox status = %#v, %v", status, err)
		}
	})

	t.Run("concurrent claim lease recovery and stale fencing", func(t *testing.T) {
		message := mustOutbound(t, "outbox-lease-recovery", []byte(`{"kind":"lease"}`), baseTime, baseTime)
		enqueue(t, ctx, runner, tenantA.ID, message)

		start := make(chan struct{})
		results := make(chan []messaging.ClaimedMessage, 2)
		errorsFound := make(chan error, 2)
		var waitGroup sync.WaitGroup
		for _, workerID := range []string{"worker-a", "worker-b"} {
			workerID := workerID
			waitGroup.Add(1)
			go func() {
				defer waitGroup.Done()
				<-start
				claimed, err := outbox.Claim(ctx, tenantA.ID, messaging.ClaimRequest{
					WorkerID:      workerID,
					BatchSize:     1,
					LeaseDuration: time.Minute,
				})
				if err != nil {
					errorsFound <- err
					return
				}
				results <- claimed
			}()
		}
		close(start)
		waitGroup.Wait()
		close(results)
		close(errorsFound)
		for err := range errorsFound {
			t.Fatalf("concurrent claim: %v", err)
		}
		var owned []messaging.ClaimedMessage
		for claimed := range results {
			owned = append(owned, claimed...)
		}
		if len(owned) != 1 || owned[0].MessageID != message.MessageID {
			t.Fatalf("concurrent owners = %#v, want one owner", owned)
		}
		firstClaim := owned[0]
		if firstClaim.FencingToken != 1 || firstClaim.AttemptCount != 1 {
			t.Fatalf("first claim token/attempt = %d/%d", firstClaim.FencingToken, firstClaim.AttemptCount)
		}

		if err := outbox.Renew(
			ctx,
			tenantA.ID,
			firstClaim.LeaseReference(),
			2*time.Minute,
		); err != nil {
			t.Fatalf("renew live lease: %v", err)
		}
		if claimed, err := outbox.Claim(ctx, tenantA.ID, messaging.ClaimRequest{
			WorkerID:      "worker-before-expiry",
			BatchSize:     1,
			LeaseDuration: time.Minute,
		}); err != nil || len(claimed) != 0 {
			t.Fatalf("claim before renewed expiry = %#v, %v", claimed, err)
		}

		expireOutboxLease(t, ctx, databaseAdminPool, tenantA.ID, message.MessageID)
		if err := outbox.Acknowledge(ctx, tenantA.ID, firstClaim.LeaseReference()); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("expired ack before reclaim = %v, want ErrLeaseLost", err)
		}
		if err := outbox.Fail(ctx, tenantA.ID, firstClaim.LeaseReference(), messaging.Failure{
			Kind: "expired_retry", RetryDelay: time.Second,
		}); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("expired retryable fail before reclaim = %v, want ErrLeaseLost", err)
		}
		if err := outbox.Renew(
			ctx,
			tenantA.ID,
			firstClaim.LeaseReference(),
			time.Minute,
		); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("expired renewal before reclaim = %v, want ErrLeaseLost", err)
		}

		secondClaims, err := outbox.Claim(ctx, tenantA.ID, messaging.ClaimRequest{
			WorkerID:      "worker-recovery",
			BatchSize:     1,
			LeaseDuration: time.Minute,
		})
		if err != nil || len(secondClaims) != 1 {
			t.Fatalf("claim expired lease = %#v, %v", secondClaims, err)
		}
		secondClaim := secondClaims[0]
		if secondClaim.FencingToken != 2 || secondClaim.AttemptCount != 2 {
			t.Fatalf("recovery token/attempt = %d/%d, want 2/2", secondClaim.FencingToken, secondClaim.AttemptCount)
		}

		if err := outbox.Acknowledge(ctx, tenantA.ID, firstClaim.LeaseReference()); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("stale ack = %v, want ErrLeaseLost", err)
		}
		if err := outbox.Fail(ctx, tenantA.ID, firstClaim.LeaseReference(), messaging.Failure{
			Kind: "stale_retry", RetryDelay: time.Second,
		}); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("stale retryable fail = %v, want ErrLeaseLost", err)
		}
		if err := outbox.Fail(ctx, tenantA.ID, firstClaim.LeaseReference(), messaging.Failure{
			Kind: "stale_terminal", Terminal: true,
		}); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("stale terminal fail = %v, want ErrLeaseLost", err)
		}
		if err := outbox.Renew(
			ctx,
			tenantA.ID,
			firstClaim.LeaseReference(),
			time.Minute,
		); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("stale renewal = %v, want ErrLeaseLost", err)
		}
		if err := outbox.Acknowledge(ctx, tenantB.ID, secondClaim.LeaseReference()); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("cross-tenant ack = %v, want ErrLeaseLost", err)
		}
		if _, err := outbox.Status(ctx, tenantB.ID, message.MessageID); !errors.Is(err, messaging.ErrMessagingNotFound) {
			t.Fatalf("cross-tenant Outbox status = %v, want not found", err)
		}
		if err := outbox.Acknowledge(ctx, tenantA.ID, secondClaim.LeaseReference()); err != nil {
			t.Fatalf("acknowledge current owner: %v", err)
		}
	})

	t.Run("lease validity is checked after a row lock wait", func(t *testing.T) {
		message := mustOutbound(
			t,
			"outbox-lock-wait-expiry",
			[]byte(`{"kind":"lock-wait"}`),
			baseTime,
			baseTime,
		)
		enqueue(t, ctx, runner, tenantA.ID, message)
		claims, err := outbox.Claim(ctx, tenantA.ID, messaging.ClaimRequest{
			WorkerID:      "worker-lock-wait",
			BatchSize:     1,
			LeaseDuration: time.Minute,
		})
		if err != nil || len(claims) != 1 {
			t.Fatalf("claim row-lock expiry message = %#v, %v", claims, err)
		}
		lease := claims[0].LeaseReference()

		lockTx, err := databaseAdminPool.Begin(ctx)
		if err != nil {
			t.Fatalf("begin Outbox row-lock transaction: %v", err)
		}
		defer func() { _ = lockTx.Rollback(context.Background()) }()
		var locked bool
		if err := lockTx.QueryRow(ctx, `
				SELECT true
				FROM agent.outbox_messages
				WHERE tenant_id = $1
				  AND message_id = $2
				FOR UPDATE
			`, tenantA.ID, message.MessageID).Scan(&locked); err != nil || !locked {
			t.Fatalf("lock Outbox lease row = %t, %v", locked, err)
		}

		ackResult := make(chan error, 1)
		go func() {
			ackResult <- outbox.Acknowledge(ctx, tenantA.ID, lease)
		}()
		waitForApplicationQueryLock(t, ctx, databaseAdminPool, "AcknowledgeOutboxMessage")

		if _, err := lockTx.Exec(ctx, `
				UPDATE agent.outbox_messages
				SET lease_expires_at = clock_timestamp() - interval '1 microsecond'
				WHERE tenant_id = $1
				  AND message_id = $2
			`, tenantA.ID, message.MessageID); err != nil {
			t.Fatalf("expire lease while holding row lock: %v", err)
		}
		if err := lockTx.Commit(ctx); err != nil {
			t.Fatalf("commit expired lease under row lock: %v", err)
		}
		if err := <-ackResult; !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("ack after lock wait crossed lease expiry = %v, want ErrLeaseLost", err)
		}
		status, err := outbox.Status(ctx, tenantA.ID, message.MessageID)
		if err != nil || status.State != messaging.OutboxLeased || !status.SucceededAt.IsZero() {
			t.Fatalf("Outbox after lock-wait expiry = %#v, %v", status, err)
		}
		recoveryClaims, err := outbox.Claim(ctx, tenantA.ID, messaging.ClaimRequest{
			WorkerID:      "worker-lock-wait-recovery",
			BatchSize:     1,
			LeaseDuration: time.Minute,
		})
		if err != nil || len(recoveryClaims) != 1 || recoveryClaims[0].MessageID != message.MessageID {
			t.Fatalf("recover lock-wait expiry message = %#v, %v", recoveryClaims, err)
		}
		if err := outbox.Acknowledge(ctx, tenantA.ID, recoveryClaims[0].LeaseReference()); err != nil {
			t.Fatalf("acknowledge recovered lock-wait expiry message: %v", err)
		}
	})

	t.Run("retry schedule and terminal reconciliation state", func(t *testing.T) {
		availableAt := baseTime.Add(time.Hour)
		message := mustOutbound(t, "outbox-retry-terminal", []byte(`{"kind":"retry"}`), availableAt, baseTime)
		enqueue(t, ctx, runner, tenantA.ID, message)
		assertDatabaseRejectsInvalidFailureKind(t, ctx, applicationPool, tenantA.ID, message.MessageID)
		claims, err := outbox.Claim(ctx, tenantA.ID, messaging.ClaimRequest{
			WorkerID:      "worker-retry",
			BatchSize:     1,
			LeaseDuration: time.Minute,
		})
		if err != nil || len(claims) != 1 {
			t.Fatalf("initial retry claim = %#v, %v", claims, err)
		}
		assertDatabaseRejectsExpiredLeaseState(t, ctx, applicationPool, tenantA.ID, message.MessageID)
		if err := outbox.Fail(ctx, tenantA.ID, claims[0].LeaseReference(), messaging.Failure{
			Kind: "dependency_unavailable", RetryDelay: time.Minute,
		}); err != nil {
			t.Fatalf("record retryable failure: %v", err)
		}
		if early, err := outbox.Claim(ctx, tenantA.ID, messaging.ClaimRequest{
			WorkerID:      "worker-early",
			BatchSize:     1,
			LeaseDuration: time.Minute,
		}); err != nil || len(early) != 0 {
			t.Fatalf("early retry claim = %#v, %v", early, err)
		}
		makeOutboxAvailable(t, ctx, databaseAdminPool, tenantA.ID, message.MessageID)
		retryClaims, err := outbox.Claim(ctx, tenantA.ID, messaging.ClaimRequest{
			WorkerID:      "worker-terminal",
			BatchSize:     1,
			LeaseDuration: time.Minute,
		})
		if err != nil || len(retryClaims) != 1 || retryClaims[0].FencingToken != 2 {
			t.Fatalf("scheduled retry claim = %#v, %v", retryClaims, err)
		}
		if err := outbox.Fail(ctx, tenantA.ID, retryClaims[0].LeaseReference(), messaging.Failure{
			Kind: "invalid_destination", Terminal: true,
		}); err != nil {
			t.Fatalf("record terminal failure: %v", err)
		}
		status, err := outbox.Status(ctx, tenantA.ID, message.MessageID)
		if err != nil || status.State != messaging.OutboxTerminalFailed || status.LastErrorKind != "invalid_destination" {
			t.Fatalf("terminal status = %#v, %v", status, err)
		}
	})

	t.Run("Inbox replay conflict rollback and one side effect", func(t *testing.T) {
		receivedAt := baseTime.Add(2 * time.Hour)
		message := mustInbound(t, tenantA.ID, "projection-a", "inbox-once", []byte(`{"value":1}`), receivedAt)
		var effectCalls atomic.Int32
		effectClient := tenancy.ClientApplication{
			TenantID: tenantA.ID, ID: "client-inbox-once", DisplayName: "Inbox Once", CreatedAt: baseTime,
		}
		effect := func(ctx context.Context, repository persistence.TenantRepository) error {
			effectCalls.Add(1)
			_, err := repository.RegisterClientApplication(ctx, tenantA, effectClient)
			return err
		}
		outcome, err := inbox.Consume(ctx, tenantA.ID, message, receivedAt.Add(time.Second), effect)
		if err != nil || outcome != messaging.ConsumeApplied {
			t.Fatalf("initial Inbox consume = %s, %v", outcome, err)
		}
		outcome, err = inbox.Consume(ctx, tenantA.ID, message, receivedAt.Add(2*time.Second), effect)
		if err != nil || outcome != messaging.ConsumeReplay || effectCalls.Load() != 1 {
			t.Fatalf("Inbox replay = %s, %v, calls %d", outcome, err, effectCalls.Load())
		}
		conflict := mustInbound(t, tenantA.ID, message.Consumer, message.MessageID, []byte(`{"value":2}`), receivedAt)
		if _, err := inbox.Consume(ctx, tenantA.ID, conflict, receivedAt.Add(3*time.Second), effect); !errors.Is(err, messaging.ErrInboxDigestConflict) {
			t.Fatalf("Inbox digest conflict = %v, want ErrInboxDigestConflict", err)
		}

		concurrentMessage := mustInbound(
			t,
			tenantA.ID,
			"projection-a",
			"inbox-concurrent",
			[]byte(`{"value":"concurrent"}`),
			receivedAt,
		)
		var concurrentCalls atomic.Int32
		concurrentClient := tenancy.ClientApplication{
			TenantID: tenantA.ID, ID: "client-inbox-concurrent", DisplayName: "Inbox Concurrent", CreatedAt: baseTime,
		}
		consumeResults := make(chan messaging.ConsumeOutcome, 2)
		consumeErrors := make(chan error, 2)
		start := make(chan struct{})
		var waitGroup sync.WaitGroup
		for range 2 {
			waitGroup.Add(1)
			go func() {
				defer waitGroup.Done()
				<-start
				outcome, err := inbox.Consume(
					ctx,
					tenantA.ID,
					concurrentMessage,
					receivedAt.Add(time.Second),
					func(ctx context.Context, repository persistence.TenantRepository) error {
						concurrentCalls.Add(1)
						_, err := repository.RegisterClientApplication(ctx, tenantA, concurrentClient)
						return err
					},
				)
				if err != nil {
					consumeErrors <- err
					return
				}
				consumeResults <- outcome
			}()
		}
		close(start)
		waitGroup.Wait()
		close(consumeResults)
		close(consumeErrors)
		for err := range consumeErrors {
			t.Fatalf("concurrent Inbox consume: %v", err)
		}
		outcomeCounts := map[messaging.ConsumeOutcome]int{}
		for outcome := range consumeResults {
			outcomeCounts[outcome]++
		}
		if outcomeCounts[messaging.ConsumeApplied] != 1 || outcomeCounts[messaging.ConsumeReplay] != 1 || concurrentCalls.Load() != 1 {
			t.Fatalf("concurrent Inbox outcomes = %#v, calls %d", outcomeCounts, concurrentCalls.Load())
		}

		rollbackMessage := mustInbound(t, tenantA.ID, "projection-a", "inbox-rollback", []byte(`{"value":"rollback"}`), receivedAt)
		rollbackClient := tenancy.ClientApplication{
			TenantID: tenantA.ID, ID: "client-inbox-rollback", DisplayName: "Inbox Rollback", CreatedAt: baseTime,
		}
		rollbackMarker := errors.New("force Inbox rollback")
		_, err = inbox.Consume(
			ctx,
			tenantA.ID,
			rollbackMessage,
			receivedAt.Add(time.Second),
			func(ctx context.Context, repository persistence.TenantRepository) error {
				if _, err := repository.RegisterClientApplication(ctx, tenantA, rollbackClient); err != nil {
					return err
				}
				return rollbackMarker
			},
		)
		if !errors.Is(err, rollbackMarker) {
			t.Fatalf("Inbox rollback = %v, want marker", err)
		}
		outcome, err = inbox.Consume(
			ctx,
			tenantA.ID,
			rollbackMessage,
			receivedAt.Add(2*time.Second),
			func(ctx context.Context, repository persistence.TenantRepository) error {
				_, err := repository.RegisterClientApplication(ctx, tenantA, rollbackClient)
				return err
			},
		)
		if err != nil || outcome != messaging.ConsumeApplied {
			t.Fatalf("Inbox consume after rolled-back effect = %s, %v", outcome, err)
		}

		tenantBMessage := mustInbound(t, tenantB.ID, "tenant-projection", "tenant-b-message", []byte(`{"tenant":"b"}`), receivedAt)
		outcome, err = inbox.Consume(ctx, tenantB.ID, tenantBMessage, receivedAt.Add(time.Second), func(context.Context, persistence.TenantRepository) error {
			return nil
		})
		if err != nil || outcome != messaging.ConsumeApplied {
			t.Fatalf("Tenant B Inbox consume = %s, %v", outcome, err)
		}
		tenantAAttack := mustInbound(t, tenantA.ID, tenantBMessage.Consumer, tenantBMessage.MessageID, tenantBMessage.Payload, receivedAt)
		var attackEffects atomic.Int32
		if _, err := inbox.Consume(ctx, tenantA.ID, tenantAAttack, receivedAt.Add(2*time.Second), func(context.Context, persistence.TenantRepository) error {
			attackEffects.Add(1)
			return nil
		}); !errors.Is(err, messaging.ErrInboxConflict) || attackEffects.Load() != 0 {
			t.Fatalf("cross-tenant Inbox consume = %v, calls %d", err, attackEffects.Load())
		}
	})

	t.Run("Tenant cannot claim renew ack or fail another Tenant message", func(t *testing.T) {
		availableAt := baseTime.Add(3 * time.Hour)
		message := mustOutbound(t, "tenant-b-outbox", []byte(`{"tenant":"b"}`), availableAt, baseTime)
		enqueue(t, ctx, runner, tenantB.ID, message)
		if claims, err := outbox.Claim(ctx, tenantA.ID, messaging.ClaimRequest{
			WorkerID:      "tenant-a-worker",
			BatchSize:     10,
			LeaseDuration: time.Minute,
		}); err != nil || len(claims) != 0 {
			t.Fatalf("Tenant A claimed Tenant B = %#v, %v", claims, err)
		}
		claims, err := outbox.Claim(ctx, tenantB.ID, messaging.ClaimRequest{
			WorkerID:      "tenant-b-worker",
			BatchSize:     1,
			LeaseDuration: time.Minute,
		})
		if err != nil || len(claims) != 1 {
			t.Fatalf("Tenant B claim = %#v, %v", claims, err)
		}
		lease := claims[0].LeaseReference()
		if err := outbox.Renew(ctx, tenantA.ID, lease, time.Minute); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("cross-tenant renew = %v, want ErrLeaseLost", err)
		}
		if err := outbox.Fail(ctx, tenantA.ID, lease, messaging.Failure{
			Kind: "cross_tenant", RetryDelay: time.Second,
		}); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("cross-tenant fail = %v, want ErrLeaseLost", err)
		}
		if err := outbox.Acknowledge(ctx, tenantA.ID, lease); !errors.Is(err, messaging.ErrLeaseLost) {
			t.Fatalf("cross-tenant ack = %v, want ErrLeaseLost", err)
		}
		if err := outbox.Acknowledge(ctx, tenantB.ID, lease); err != nil {
			t.Fatalf("Tenant B ack: %v", err)
		}
	})

	assertPoolTenantContextEmpty(t, ctx, applicationPool)
	runGoose(t, databaseAdminDSN, "down", true)
	assertMigrationVersion(t, databaseAdminDSN, 2)
	downOutput := runGoose(t, databaseAdminDSN, "down", false)
	if !strings.Contains(downOutput, "contains durable data and is forward-only") {
		t.Fatalf("data-bearing durable messaging Down lacks classification: %s", downOutput)
	}
	assertMigrationVersion(t, databaseAdminDSN, 2)
	assertBaselineTableSecurity(t, ctx, databaseAdminPool)
	if _, err := outbox.Status(ctx, tenantA.ID, "tenant-b-outbox"); !errors.Is(err, messaging.ErrMessagingNotFound) {
		t.Fatalf("cross-tenant Outbox status after refused Down = %v, want not found", err)
	}
	if status, err := outbox.Status(ctx, tenantB.ID, "tenant-b-outbox"); err != nil || status.State != messaging.OutboxSucceeded {
		t.Fatalf("Tenant B Outbox status after refused Down = %#v, %v", status, err)
	}
	runGoose(t, databaseAdminDSN, "up", true)
	assertMigrationVersion(t, databaseAdminDSN, 3)
}

func assertDatabaseRejectsInvalidFailureKind(
	t *testing.T,
	ctx context.Context,
	applicationPool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	messageID string,
) {
	t.Helper()
	invalidKinds := []string{
		"Raw Provider Error",
		"retry\n",
		"non_ascii_" + string(rune(0x00e9)),
	}
	for _, invalidKind := range invalidKinds {
		tx, err := applicationPool.Begin(ctx)
		if err != nil {
			t.Fatalf("begin invalid failure-kind probe: %v", err)
		}
		if _, err := tx.Exec(ctx, "SELECT set_config('agent.tenant_id', $1, true)", string(tenantID)); err != nil {
			_ = tx.Rollback(context.Background())
			t.Fatalf("set invalid failure-kind probe TenantContext: %v", err)
		}
		_, err = tx.Exec(ctx, `
			UPDATE agent.outbox_messages
			SET last_error_kind = $3,
			    last_error_at = clock_timestamp()
			WHERE tenant_id = $1
			  AND message_id = $2
		`, tenantID, messageID, invalidKind)
		var databaseError *pgconn.PgError
		if !errors.As(err, &databaseError) || databaseError.ConstraintName != "outbox_messages_error_kind" {
			_ = tx.Rollback(context.Background())
			t.Fatalf("invalid database failure kind %q = %v, want outbox_messages_error_kind violation", invalidKind, err)
		}
		if err := tx.Rollback(context.Background()); err != nil {
			t.Fatalf("rollback invalid failure-kind probe: %v", err)
		}
	}
}

func assertDatabaseRejectsExpiredLeaseState(
	t *testing.T,
	ctx context.Context,
	applicationPool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	messageID string,
) {
	t.Helper()
	tx, err := applicationPool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin invalid lease-state probe: %v", err)
	}
	defer func() { _ = tx.Rollback(context.Background()) }()
	if _, err := tx.Exec(ctx, "SELECT set_config('agent.tenant_id', $1, true)", string(tenantID)); err != nil {
		t.Fatalf("set invalid lease-state probe TenantContext: %v", err)
	}
	_, err = tx.Exec(ctx, `
		UPDATE agent.outbox_messages
		SET lease_expires_at = updated_at
		WHERE tenant_id = $1
		  AND message_id = $2
	`, tenantID, messageID)
	var databaseError *pgconn.PgError
	if !errors.As(err, &databaseError) || databaseError.ConstraintName != "outbox_messages_state_fields" {
		t.Fatalf("invalid leased expiry = %v, want outbox_messages_state_fields violation", err)
	}
}

func waitForApplicationQueryLock(
	t *testing.T,
	ctx context.Context,
	adminPool *pgxpool.Pool,
	queryName string,
) {
	t.Helper()
	waitCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	for {
		var blocked bool
		err := adminPool.QueryRow(waitCtx, `
			SELECT EXISTS (
				SELECT 1
				FROM pg_stat_activity
				WHERE usename = $1
				  AND state = 'active'
				  AND wait_event_type = 'Lock'
				  AND query LIKE '%' || $2 || '%'
			)
		`, applicationLogin, queryName).Scan(&blocked)
		if err != nil {
			t.Fatalf("wait for %s row lock: %v", queryName, err)
		}
		if blocked {
			return
		}
		if err := waitCtx.Err(); err != nil {
			t.Fatalf("wait for %s row lock: %v", queryName, err)
		}
	}
}

func expireOutboxLease(
	t *testing.T,
	ctx context.Context,
	adminPool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	messageID string,
) {
	t.Helper()
	result, err := adminPool.Exec(ctx, `
		UPDATE agent.outbox_messages
		SET updated_at = clock_timestamp() - interval '2 seconds',
		    lease_expires_at = clock_timestamp() - interval '1 second'
		WHERE tenant_id = $1
		  AND message_id = $2
		  AND state = 'leased'
	`, tenantID, messageID)
	if err != nil {
		t.Fatalf("expire Outbox lease: %v", err)
	}
	if result.RowsAffected() != 1 {
		t.Fatalf("expired Outbox leases = %d, want 1", result.RowsAffected())
	}
}

func makeOutboxAvailable(
	t *testing.T,
	ctx context.Context,
	adminPool *pgxpool.Pool,
	tenantID tenancy.TenantID,
	messageID string,
) {
	t.Helper()
	result, err := adminPool.Exec(ctx, `
		UPDATE agent.outbox_messages
		SET next_attempt_at = clock_timestamp() - interval '1 second'
		WHERE tenant_id = $1
		  AND message_id = $2
		  AND state = 'pending'
	`, tenantID, messageID)
	if err != nil {
		t.Fatalf("make Outbox message available: %v", err)
	}
	if result.RowsAffected() != 1 {
		t.Fatalf("available Outbox messages = %d, want 1", result.RowsAffected())
	}
}

func registerClient(
	t *testing.T,
	ctx context.Context,
	repository *persistence.ClientApplicationRepository,
	tenant tenancy.Tenant,
	clientID tenancy.ClientApplicationID,
	createdAt time.Time,
) {
	t.Helper()
	if _, err := repository.Register(ctx, tenant, tenancy.ClientApplication{
		TenantID:    tenant.ID,
		ID:          clientID,
		DisplayName: string(clientID),
		CreatedAt:   createdAt,
	}); err != nil {
		t.Fatalf("register %s/%s: %v", tenant.ID, clientID, err)
	}
}

func mustOutbound(
	t *testing.T,
	messageID string,
	payload []byte,
	availableAt time.Time,
	createdAt time.Time,
) messaging.OutboundMessage {
	t.Helper()
	message, err := messaging.NewOutboundMessage(
		messageID,
		"transport-consumer",
		payload,
		availableAt,
		createdAt,
	)
	if err != nil {
		t.Fatalf("create outbound message %s: %v", messageID, err)
	}
	return message
}

func enqueue(
	t *testing.T,
	ctx context.Context,
	runner *persistence.TransactionRunner,
	tenantID tenancy.TenantID,
	message messaging.OutboundMessage,
) {
	t.Helper()
	if err := runner.Run(ctx, tenantID, func(
		ctx context.Context,
		repository persistence.TenantRepository,
	) error {
		outcome, err := repository.EnqueueOutboxMessage(ctx, message)
		if err != nil {
			return err
		}
		if outcome != messaging.EnqueueInserted {
			t.Fatalf("enqueue %s outcome = %s, want inserted", message.MessageID, outcome)
		}
		return nil
	}); err != nil {
		t.Fatalf("enqueue %s: %v", message.MessageID, err)
	}
}

func mustInbound(
	t *testing.T,
	tenantID tenancy.TenantID,
	consumer string,
	messageID string,
	payload []byte,
	receivedAt time.Time,
) messaging.InboundMessage {
	t.Helper()
	message, err := messaging.NewInboundMessage(
		tenantID,
		consumer,
		messageID,
		payload,
		receivedAt,
	)
	if err != nil {
		t.Fatalf("create inbound message %s: %v", messageID, err)
	}
	return message
}
