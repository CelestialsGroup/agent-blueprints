//go:build integration

package integration_test

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shell-echo/agent/internal/domain/tenancy"
	"github.com/shell-echo/agent/internal/persistence"
)

const (
	agentDatabase     = "agent_integration"
	forbiddenDatabase = "agent_second_database"
	applicationLogin  = "agent_app_integration"
	applicationPass   = "b021-integration-application"
	migratorLogin     = "agent_migrator_integration"
	migratorPass      = "b021-integration-migrator"
)

func TestBootstrapMigrationRejectsDestructiveDownAndRemainsUp(t *testing.T) {
	ctx := context.Background()
	adminDSN := requiredEnv(t, "AGENT_TEST_ADMIN_DSN")
	adminPool := openPool(t, adminDSN, 2)
	createDatabase(t, ctx, adminPool, agentDatabase)
	t.Cleanup(func() { dropDatabase(t, adminPool, agentDatabase) })

	databaseDSN := replaceDatabase(t, adminDSN, agentDatabase, "postgres", "b021-integration-admin")
	runGoose(t, databaseDSN, "up", true)
	assertMigrationVersion(t, databaseDSN, 1)

	downOutput := runGoose(t, databaseDSN, "down", false)
	if !strings.Contains(downOutput, "forward-only") {
		t.Fatalf("down failure did not report forward-only classification: %s", downOutput)
	}
	assertMigrationVersion(t, databaseDSN, 1)
	assertBootstrapTables(t, databaseDSN)

	runGoose(t, databaseDSN, "up", true)
	assertMigrationVersion(t, databaseDSN, 1)

	createDatabase(t, ctx, adminPool, forbiddenDatabase)
	t.Cleanup(func() { dropDatabase(t, adminPool, forbiddenDatabase) })
	forbiddenDSN := replaceDatabase(t, adminDSN, forbiddenDatabase, "postgres", "b021-integration-admin")
	output := runGoose(t, forbiddenDSN, "up", false)
	if !strings.Contains(output, "not database "+forbiddenDatabase) {
		t.Fatalf("second Agent database rejection did not report the role binding: %s", output)
	}
	assertAgentSchemaAbsent(t, forbiddenDSN)
}

func TestTenantTransactionAndRLSIsolation(t *testing.T) {
	ctx := context.Background()
	adminDSN := requiredEnv(t, "AGENT_TEST_ADMIN_DSN")
	adminPool := openPool(t, adminDSN, 2)
	createDatabase(t, ctx, adminPool, agentDatabase)
	t.Cleanup(func() { dropDatabase(t, adminPool, agentDatabase) })

	databaseAdminDSN := replaceDatabase(t, adminDSN, agentDatabase, "postgres", "b021-integration-admin")
	runGoose(t, databaseAdminDSN, "up", true)
	databaseAdminPool := openPool(t, databaseAdminDSN, 2)
	assertRoleProfiles(t, ctx, databaseAdminPool)
	assertTableSecurity(t, ctx, databaseAdminPool)
	assertExactApplicationPrivileges(t, ctx, databaseAdminPool)
	createMigratorLogin(t, ctx, databaseAdminPool)
	assertMigratorGoosePath(t, databaseAdminDSN, adminDSN, databaseAdminPool)
	createApplicationLogin(t, ctx, databaseAdminPool)

	applicationDSN := replaceDatabase(t, adminDSN, agentDatabase, applicationLogin, applicationPass)
	applicationPool := openPool(t, applicationDSN, 1)
	runner, err := persistence.NewTransactionRunner(applicationPool)
	if err != nil {
		t.Fatalf("create transaction runner: %v", err)
	}
	repository, err := persistence.NewClientApplicationRepository(runner)
	if err != nil {
		t.Fatalf("create repository: %v", err)
	}

	createdAt := time.Date(2026, time.July, 22, 0, 0, 0, 0, time.UTC)
	tenantA := tenancy.Tenant{ID: "tenant-a", DisplayName: "Tenant A", CreatedAt: createdAt}
	tenantB := tenancy.Tenant{ID: "tenant-b", DisplayName: "Tenant B", CreatedAt: createdAt}
	clientA := tenancy.ClientApplication{
		TenantID: tenantA.ID, ID: "client-a", DisplayName: "Client A", CreatedAt: createdAt,
	}
	clientB := tenancy.ClientApplication{
		TenantID: tenantB.ID, ID: "client-b", DisplayName: "Client B", CreatedAt: createdAt,
	}

	if _, err := repository.Register(ctx, tenantA, clientA); err != nil {
		t.Fatalf("register tenant A client: %v", err)
	}
	if _, err := repository.Register(ctx, tenantB, clientB); err != nil {
		t.Fatalf("register tenant B client: %v", err)
	}
	assertTenantMetadataConflictRollsBack(t, ctx, repository, tenantA, createdAt)
	if _, err := repository.Find(ctx, tenantA.ID, clientA.ID); err != nil {
		t.Fatalf("tenant A cannot read its own client: %v", err)
	}
	if _, err := repository.Find(ctx, tenantA.ID, clientB.ID); !errors.Is(err, persistence.ErrNotFound) {
		t.Fatalf("tenant A cross-tenant read = %v, want ErrNotFound", err)
	}

	if _, err := repository.Find(ctx, "", clientA.ID); !errors.Is(err, tenancy.ErrMissingTenantContext) {
		t.Fatalf("missing tenant context = %v, want ErrMissingTenantContext", err)
	}
	invalidTenantID := tenancy.TenantID(strings.Repeat("x", 201))
	if _, err := repository.Find(ctx, invalidTenantID, clientA.ID); !errors.Is(err, tenancy.ErrInvalidTenantID) {
		t.Fatalf("invalid tenant context = %v, want ErrInvalidTenantID", err)
	}
	assertMissingContextFailsClosed(t, ctx, applicationPool)
	assertInvalidContextFailsClosed(t, ctx, applicationPool)
	assertCrossTenantReadWriteDenied(t, ctx, applicationPool)
	assertApplicationCannotBypassOrDDL(t, ctx, applicationPool)
	assertNestedTransactionRejected(t, ctx, runner, tenantA.ID)
	assertRepositoryCannotEscapeTransaction(t, ctx, runner, tenantA.ID, clientA.ID)
	assertCommitAndRollbackDoNotLeak(t, ctx, runner, applicationPool, tenantA, clientA, createdAt)
}

func assertInvalidContextFailsClosed(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin invalid-context transaction: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(
		ctx,
		"SELECT set_config('agent.tenant_id', $1, true)",
		strings.Repeat("x", 201),
	); err != nil {
		t.Fatalf("set invalid tenant context: %v", err)
	}
	var count int
	if err := tx.QueryRow(ctx, "SELECT count(*) FROM agent.client_applications").Scan(&count); err != nil {
		t.Fatalf("invalid-context read returned an unexpected error: %v", err)
	}
	if count != 0 {
		t.Fatalf("invalid-context read returned %d rows, want 0", count)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO agent.tenants (tenant_id, display_name, created_at)
		VALUES ('tenant-invalid', 'Invalid', '2026-07-22T00:00:00Z')
	`); err == nil {
		t.Fatal("invalid-context write unexpectedly succeeded")
	}
}

func assertMissingContextFailsClosed(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	var count int
	if err := pool.QueryRow(ctx, "SELECT count(*) FROM agent.client_applications").Scan(&count); err != nil {
		t.Fatalf("missing-context read returned an unexpected error: %v", err)
	}
	if count != 0 {
		t.Fatalf("missing-context read returned %d rows, want 0", count)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO agent.tenants (tenant_id, display_name, created_at)
		VALUES ('tenant-missing', 'Missing', '2026-07-22T00:00:00Z')
	`); err == nil {
		t.Fatal("missing-context write unexpectedly succeeded")
	}
}

func assertCrossTenantReadWriteDenied(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin cross-tenant attack transaction: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, "SELECT set_config('agent.tenant_id', $1, true)", "tenant-a"); err != nil {
		t.Fatalf("set tenant A attack context: %v", err)
	}
	var count int
	if err := tx.QueryRow(ctx, `
		SELECT count(*)
		FROM agent.client_applications
		WHERE tenant_id = 'tenant-b'
	`).Scan(&count); err != nil {
		t.Fatalf("tenant A cross-tenant read returned an unexpected error: %v", err)
	}
	if count != 0 {
		t.Fatalf("tenant A cross-tenant read returned %d rows, want 0", count)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO agent.client_applications
		    (tenant_id, client_app_id, display_name, created_at)
		VALUES ('tenant-b', 'client-cross-tenant', 'Cross Tenant', '2026-07-22T00:00:00Z')
	`); err == nil {
		t.Fatal("tenant A wrote a tenant B row")
	}
}

func assertApplicationCannotBypassOrDDL(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	if _, err := pool.Exec(ctx, "UPDATE agent.tenants SET display_name = 'forbidden'"); err == nil {
		t.Fatal("application role updated tenant rows")
	}
	if _, err := pool.Exec(ctx, "DELETE FROM agent.client_applications"); err == nil {
		t.Fatal("application role deleted client application rows")
	}
	if _, err := pool.Exec(ctx, "CREATE TABLE agent.forbidden_ddl (id integer)"); err == nil {
		t.Fatal("application role created a persistent table")
	}
	if _, err := pool.Exec(ctx, "CREATE TABLE public.forbidden_ddl (id integer)"); err == nil {
		t.Fatal("application role created a persistent table in public")
	}
	if _, err := pool.Exec(ctx, "CREATE TEMPORARY TABLE forbidden_temp (id integer)"); err == nil {
		t.Fatal("application role created a temporary table")
	}
	if _, err := pool.Exec(ctx, "ALTER TABLE agent.tenants DISABLE ROW LEVEL SECURITY"); err == nil {
		t.Fatal("application role disabled RLS")
	}
	if _, err := pool.Exec(ctx, "SET ROLE agent_migrator"); err == nil {
		t.Fatal("application role switched to the Migrator role")
	}
	if _, err := pool.Exec(ctx, "ALTER ROLE agent_app BYPASSRLS"); err == nil {
		t.Fatal("application role granted itself BYPASSRLS")
	}

	connection, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("acquire application connection: %v", err)
	}
	defer connection.Release()
	if _, err := connection.Exec(ctx, "SET row_security = off"); err != nil {
		t.Fatalf("set row_security off: %v", err)
	}
	defer func() { _, _ = connection.Exec(ctx, "SET row_security = on") }()
	if err := connection.QueryRow(ctx, "SELECT count(*) FROM agent.tenants").Scan(new(int)); err == nil {
		t.Fatal("application role bypassed FORCE RLS with row_security=off")
	}
}

func assertTenantMetadataConflictRollsBack(
	t *testing.T,
	ctx context.Context,
	repository *persistence.ClientApplicationRepository,
	tenant tenancy.Tenant,
	createdAt time.Time,
) {
	t.Helper()
	cases := []struct {
		name     string
		tenant   tenancy.Tenant
		clientID tenancy.ClientApplicationID
	}{
		{
			name: "display name",
			tenant: tenancy.Tenant{
				ID: tenant.ID, DisplayName: "Conflicting Name", CreatedAt: tenant.CreatedAt,
			},
			clientID: "client-conflicting-name",
		},
		{
			name: "creation time",
			tenant: tenancy.Tenant{
				ID: tenant.ID, DisplayName: tenant.DisplayName, CreatedAt: createdAt.Add(time.Second),
			},
			clientID: "client-conflicting-time",
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			application := tenancy.ClientApplication{
				TenantID:    tenant.ID,
				ID:          testCase.clientID,
				DisplayName: "Must Not Persist",
				CreatedAt:   createdAt,
			}
			_, err := repository.Register(ctx, testCase.tenant, application)
			if !errors.Is(err, persistence.ErrTenantConflict) {
				t.Fatalf("tenant metadata conflict = %v, want ErrTenantConflict", err)
			}
			var conflict *persistence.TenantConflictError
			if !errors.As(err, &conflict) || conflict.TenantID != tenant.ID {
				t.Fatalf("tenant metadata conflict details = %#v, want tenant %s", conflict, tenant.ID)
			}
			if _, err := repository.Find(ctx, tenant.ID, application.ID); !errors.Is(err, persistence.ErrNotFound) {
				t.Fatalf("client application persisted after tenant conflict: %v", err)
			}
		})
	}
}

func assertRepositoryCannotEscapeTransaction(
	t *testing.T,
	ctx context.Context,
	runner *persistence.TransactionRunner,
	tenantID tenancy.TenantID,
	clientApplicationID tenancy.ClientApplicationID,
) {
	t.Helper()
	var escapedContext context.Context
	var escapedRepository persistence.TenantRepository
	if err := runner.Run(ctx, tenantID, func(
		tenantCtx context.Context,
		repository persistence.TenantRepository,
	) error {
		escapedContext = tenantCtx
		escapedRepository = repository
		return nil
	}); err != nil {
		t.Fatalf("capture tenant repository: %v", err)
	}
	if _, err := escapedRepository.FindClientApplication(
		escapedContext,
		clientApplicationID,
	); !errors.Is(err, persistence.ErrRepositoryOutsideTransaction) {
		t.Fatalf("escaped tenant repository = %v, want ErrRepositoryOutsideTransaction", err)
	}
}

func assertNestedTransactionRejected(
	t *testing.T,
	ctx context.Context,
	runner *persistence.TransactionRunner,
	tenantID tenancy.TenantID,
) {
	t.Helper()
	err := runner.Run(ctx, tenantID, func(innerCtx context.Context, _ persistence.TenantRepository) error {
		return runner.Run(innerCtx, tenantID, func(context.Context, persistence.TenantRepository) error {
			return nil
		})
	})
	if !errors.Is(err, persistence.ErrNestedTransaction) {
		t.Fatalf("nested transaction = %v, want ErrNestedTransaction", err)
	}
}

func assertCommitAndRollbackDoNotLeak(
	t *testing.T,
	ctx context.Context,
	runner *persistence.TransactionRunner,
	pool *pgxpool.Pool,
	tenant tenancy.Tenant,
	application tenancy.ClientApplication,
	createdAt time.Time,
) {
	t.Helper()
	if err := runner.Run(ctx, tenant.ID, func(
		ctx context.Context,
		repository persistence.TenantRepository,
	) error {
		_, err := repository.FindClientApplication(ctx, application.ID)
		return err
	}); err != nil {
		t.Fatalf("committed tenant transaction: %v", err)
	}
	assertPoolTenantContextEmpty(t, ctx, pool)

	rollbackMarker := errors.New("force rollback")
	rollbackTenant := tenancy.Tenant{ID: "tenant-rollback", DisplayName: "Rollback", CreatedAt: createdAt}
	rollbackClient := tenancy.ClientApplication{
		TenantID: rollbackTenant.ID, ID: "client-rollback", DisplayName: "Rollback", CreatedAt: createdAt,
	}
	err := runner.Run(ctx, rollbackTenant.ID, func(
		ctx context.Context,
		repository persistence.TenantRepository,
	) error {
		if _, err := repository.RegisterClientApplication(ctx, rollbackTenant, rollbackClient); err != nil {
			return err
		}
		return rollbackMarker
	})
	if !errors.Is(err, rollbackMarker) {
		t.Fatalf("rollback transaction = %v, want marker", err)
	}
	assertPoolTenantContextEmpty(t, ctx, pool)

	err = runner.Run(ctx, rollbackTenant.ID, func(
		ctx context.Context,
		repository persistence.TenantRepository,
	) error {
		_, err := repository.FindClientApplication(ctx, rollbackClient.ID)
		return err
	})
	if !errors.Is(err, persistence.ErrNotFound) {
		t.Fatalf("rolled-back client lookup = %v, want ErrNotFound", err)
	}
}

func assertPoolTenantContextEmpty(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	connection, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("acquire reused connection: %v", err)
	}
	defer connection.Release()
	var tenantSetting string
	if err := connection.QueryRow(
		ctx,
		"SELECT COALESCE(current_setting('agent.tenant_id', true), '')",
	).Scan(&tenantSetting); err != nil {
		t.Fatalf("read reused connection tenant setting: %v", err)
	}
	if tenantSetting != "" {
		t.Fatalf("reused connection retained tenant context %q", tenantSetting)
	}
	var count int
	if err := connection.QueryRow(ctx, "SELECT count(*) FROM agent.client_applications").Scan(&count); err != nil {
		t.Fatalf("read through reused connection without context: %v", err)
	}
	if count != 0 {
		t.Fatalf("reused connection without context exposed %d rows", count)
	}
}

func assertRoleProfiles(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	for _, role := range []string{"agent_migrator", "agent_app"} {
		var canLogin, superuser, inherit, createRole, createDB, replication, bypassRLS bool
		if err := pool.QueryRow(ctx, `
			SELECT rolcanlogin, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls
			FROM pg_roles
			WHERE rolname = $1
		`, role).Scan(&canLogin, &superuser, &inherit, &createRole, &createDB, &replication, &bypassRLS); err != nil {
			t.Fatalf("read role %s: %v", role, err)
		}
		if canLogin || superuser || inherit || createRole || createDB || replication || bypassRLS {
			t.Fatalf("role %s has an elevated attribute", role)
		}
	}
	var inheritedRoleCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM pg_auth_members AS membership
		JOIN pg_roles AS member_role ON member_role.oid = membership.member
		WHERE member_role.rolname IN ('agent_migrator', 'agent_app')
	`).Scan(&inheritedRoleCount); err != nil {
		t.Fatalf("read database role memberships: %v", err)
	}
	if inheritedRoleCount != 0 {
		t.Fatalf("database roles inherit %d roles, want 0", inheritedRoleCount)
	}
	for _, role := range []string{"agent_migrator", "agent_app"} {
		var binding string
		if err := pool.QueryRow(ctx, `
			SELECT shobj_description(oid, 'pg_authid')
			FROM pg_roles
			WHERE rolname = $1
		`, role).Scan(&binding); err != nil {
			t.Fatalf("read role binding for %s: %v", role, err)
		}
		if binding != "agent_database="+agentDatabase {
			t.Fatalf("role %s binding = %q, want database %s", role, binding, agentDatabase)
		}
	}
}

func assertTableSecurity(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	rows, err := pool.Query(ctx, `
		SELECT c.relname, owner.rolname, c.relrowsecurity, c.relforcerowsecurity
		FROM pg_class AS c
		JOIN pg_namespace AS namespace ON namespace.oid = c.relnamespace
		JOIN pg_roles AS owner ON owner.oid = c.relowner
		WHERE namespace.nspname = 'agent'
		  AND c.relname IN ('tenants', 'client_applications')
		ORDER BY c.relname
	`)
	if err != nil {
		t.Fatalf("query table security: %v", err)
	}
	defer rows.Close()
	count := 0
	for rows.Next() {
		var table, owner string
		var rlsEnabled, rlsForced bool
		if err := rows.Scan(&table, &owner, &rlsEnabled, &rlsForced); err != nil {
			t.Fatalf("scan table security: %v", err)
		}
		if owner != "agent_migrator" || !rlsEnabled || !rlsForced {
			t.Fatalf("table %s owner/RLS = %s/%t/%t", table, owner, rlsEnabled, rlsForced)
		}
		count++
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate table security: %v", err)
	}
	if count != 2 {
		t.Fatalf("secured table count = %d, want 2", count)
	}
}

func assertExactApplicationPrivileges(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	for _, table := range []string{"agent.tenants", "agent.client_applications"} {
		for _, privilege := range []string{"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"} {
			var granted bool
			if err := pool.QueryRow(
				ctx,
				"SELECT has_table_privilege('agent_app', $1, $2)",
				table,
				privilege,
			).Scan(&granted); err != nil {
				t.Fatalf("read %s %s privilege: %v", table, privilege, err)
			}
			want := privilege == "SELECT" || privilege == "INSERT"
			if granted != want {
				t.Fatalf("agent_app %s on %s = %t, want %t", privilege, table, granted, want)
			}
		}
	}

	checks := []struct {
		query string
		want  bool
	}{
		{"SELECT has_schema_privilege('agent_app', 'agent', 'USAGE')", true},
		{"SELECT has_schema_privilege('agent_app', 'agent', 'CREATE')", false},
		{"SELECT has_database_privilege('agent_app', current_database(), 'CONNECT')", true},
		{"SELECT has_database_privilege('agent_app', current_database(), 'CREATE')", false},
		{"SELECT has_database_privilege('agent_app', current_database(), 'TEMP')", false},
	}
	for _, check := range checks {
		var granted bool
		if err := pool.QueryRow(ctx, check.query).Scan(&granted); err != nil {
			t.Fatalf("read application privilege with %q: %v", check.query, err)
		}
		if granted != check.want {
			t.Fatalf("application privilege %q = %t, want %t", check.query, granted, check.want)
		}
	}
}

func createApplicationLogin(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	_, err := pool.Exec(ctx, fmt.Sprintf(`
		CREATE ROLE %s LOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE
		    NOREPLICATION NOBYPASSRLS PASSWORD '%s';
		GRANT agent_app TO %s;
	`, applicationLogin, applicationPass, applicationLogin))
	if err != nil {
		t.Fatalf("create application test login: %v", err)
	}
}

func createMigratorLogin(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	_, err := pool.Exec(ctx, fmt.Sprintf(`
		CREATE ROLE %s LOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE
		    NOREPLICATION NOBYPASSRLS PASSWORD '%s';
		GRANT agent_migrator TO %s;
	`, migratorLogin, migratorPass, migratorLogin))
	if err != nil {
		t.Fatalf("create migrator test login: %v", err)
	}
}

func assertMigratorGoosePath(
	t *testing.T,
	databaseAdminDSN string,
	clusterAdminDSN string,
	adminPool *pgxpool.Pool,
) {
	t.Helper()
	migrationDirectory, err := filepath.Abs("testdata/migration")
	if err != nil {
		t.Fatalf("resolve migrator probe directory: %v", err)
	}
	migratorDSN := replaceDatabase(t, clusterAdminDSN, agentDatabase, migratorLogin, migratorPass)
	runGooseInDirectory(t, migratorDSN, migrationDirectory, "up", true, true)
	assertMigrationVersion(t, databaseAdminDSN, 2)

	var owner string
	if err := adminPool.QueryRow(context.Background(), `
		SELECT owner.rolname
		FROM pg_class AS object
		JOIN pg_namespace AS namespace ON namespace.oid = object.relnamespace
		JOIN pg_roles AS owner ON owner.oid = object.relowner
		WHERE namespace.nspname = 'agent'
		  AND object.relname = 'migrator_role_probe'
	`).Scan(&owner); err != nil {
		t.Fatalf("read migrator probe owner: %v", err)
	}
	if owner != "agent_migrator" {
		t.Fatalf("migrator probe owner = %s, want agent_migrator", owner)
	}

	runGooseInDirectory(t, migratorDSN, migrationDirectory, "down", true, true)
	assertMigrationVersion(t, databaseAdminDSN, 1)
	var exists bool
	if err := adminPool.QueryRow(context.Background(), `
		SELECT to_regclass('agent.migrator_role_probe') IS NOT NULL
	`).Scan(&exists); err != nil {
		t.Fatalf("check migrator probe rollback: %v", err)
	}
	if exists {
		t.Fatal("migrator probe table remained after goose rollback")
	}
}

func createDatabase(t *testing.T, ctx context.Context, adminPool *pgxpool.Pool, database string) {
	t.Helper()
	if _, err := adminPool.Exec(ctx, "CREATE DATABASE "+pgx.Identifier{database}.Sanitize()); err != nil {
		t.Fatalf("create database %s: %v", database, err)
	}
}

func dropDatabase(t *testing.T, adminPool *pgxpool.Pool, database string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_, _ = adminPool.Exec(ctx, "DROP DATABASE IF EXISTS "+pgx.Identifier{database}.Sanitize()+" WITH (FORCE)")
}

func runGoose(t *testing.T, dsn string, operation string, wantSuccess bool) string {
	t.Helper()
	migrationDirectory, err := filepath.Abs("../../db/migration")
	if err != nil {
		t.Fatalf("resolve migration directory: %v", err)
	}
	return runGooseInDirectory(t, dsn, migrationDirectory, operation, wantSuccess, false)
}

func runGooseInDirectory(
	t *testing.T,
	dsn string,
	migrationDirectory string,
	operation string,
	wantSuccess bool,
	allowMissing bool,
) string {
	t.Helper()
	goose := requiredEnv(t, "AGENT_GOOSE")
	arguments := []string{"-dir", migrationDirectory}
	if allowMissing {
		arguments = append(arguments, "-allow-missing")
	}
	arguments = append(arguments, "postgres", dsn, operation)
	command := exec.Command(goose, arguments...)
	output, commandErr := command.CombinedOutput()
	if wantSuccess && commandErr != nil {
		t.Fatalf("goose %s failed: %v\n%s", operation, commandErr, output)
	}
	if !wantSuccess && commandErr == nil {
		t.Fatalf("goose %s unexpectedly succeeded:\n%s", operation, output)
	}
	return string(output)
}

func assertAgentSchemaAbsent(t *testing.T, dsn string) {
	t.Helper()
	pool := openPool(t, dsn, 1)
	var exists bool
	if err := pool.QueryRow(context.Background(), `
		SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'agent')
	`).Scan(&exists); err != nil {
		t.Fatalf("check rejected database schema: %v", err)
	}
	if exists {
		t.Fatal("rejected second Agent database contains the agent schema")
	}
}

func assertMigrationVersion(t *testing.T, dsn string, version int64) {
	t.Helper()
	pool := openPool(t, dsn, 1)
	var actual int64
	if err := pool.QueryRow(context.Background(), `
		SELECT version_id
		FROM public.goose_db_version
		WHERE is_applied
		ORDER BY id DESC
		LIMIT 1
	`).Scan(&actual); err != nil {
		t.Fatalf("read goose version: %v", err)
	}
	if actual != version {
		t.Fatalf("goose version = %d, want %d", actual, version)
	}
}

func assertBootstrapTables(t *testing.T, dsn string) {
	t.Helper()
	pool := openPool(t, dsn, 1)
	var count int
	if err := pool.QueryRow(context.Background(), `
		SELECT count(*)
		FROM information_schema.tables
		WHERE table_schema = 'agent'
		  AND table_name IN ('tenants', 'client_applications')
	`).Scan(&count); err != nil {
		t.Fatalf("read bootstrap tables: %v", err)
	}
	if count != 2 {
		t.Fatalf("bootstrap table count = %d, want 2", count)
	}
}

func openPool(t *testing.T, dsn string, maxConnections int32) *pgxpool.Pool {
	t.Helper()
	config, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		t.Fatalf("parse PostgreSQL DSN: %v", err)
	}
	config.MaxConns = maxConnections
	pool, err := pgxpool.NewWithConfig(context.Background(), config)
	if err != nil {
		t.Fatalf("open PostgreSQL pool: %v", err)
	}
	if err := pool.Ping(context.Background()); err != nil {
		pool.Close()
		t.Fatalf("ping PostgreSQL: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func replaceDatabase(t *testing.T, dsn, database, username, password string) string {
	t.Helper()
	parsed, err := url.Parse(dsn)
	if err != nil {
		t.Fatalf("parse admin DSN: %v", err)
	}
	parsed.Path = "/" + database
	parsed.User = url.UserPassword(username, password)
	return parsed.String()
}

func requiredEnv(t *testing.T, name string) string {
	t.Helper()
	value := os.Getenv(name)
	if value == "" {
		t.Fatalf("%s is required", name)
	}
	return value
}
