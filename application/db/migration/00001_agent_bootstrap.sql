-- Bootstrap-admin migration: creates cluster roles and database-local objects on an
-- empty database. It takes only catalog/object-creation locks and moves no data.
-- Runtime workloads use LOGIN roles provisioned outside this file and inherit one
-- of the NOLOGIN group roles created here. Rollback is forward-only because role,
-- ownership, and database privilege changes cannot be safely inferred or erased.
-- +goose Up
-- +goose StatementBegin
DO $bootstrap_roles$
DECLARE
    role_record record;
    role_binding text := format('agent_database=%s', current_database());
    existing_binding text;
BEGIN
    SELECT rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin, rolreplication, rolbypassrls
      INTO role_record
      FROM pg_roles
     WHERE rolname = 'agent_migrator';

    IF NOT FOUND THEN
        CREATE ROLE agent_migrator
            NOLOGIN NOSUPERUSER NOINHERIT NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
        EXECUTE format('COMMENT ON ROLE agent_migrator IS %L', role_binding);
    ELSIF role_record.rolsuper
       OR role_record.rolinherit
       OR role_record.rolcreaterole
       OR role_record.rolcreatedb
       OR role_record.rolcanlogin
       OR role_record.rolreplication
       OR role_record.rolbypassrls THEN
        RAISE EXCEPTION 'existing agent_migrator role violates the bootstrap role profile';
    END IF;

    SELECT shobj_description(oid, 'pg_authid')
      INTO existing_binding
      FROM pg_roles
     WHERE rolname = 'agent_migrator';
    IF existing_binding IS DISTINCT FROM role_binding THEN
        RAISE EXCEPTION
            'agent_migrator is bound to %, not database %',
            coalesce(existing_binding, '<unbound>'),
            current_database();
    END IF;

    SELECT rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin, rolreplication, rolbypassrls
      INTO role_record
      FROM pg_roles
     WHERE rolname = 'agent_app';

    IF NOT FOUND THEN
        CREATE ROLE agent_app
            NOLOGIN NOSUPERUSER NOINHERIT NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
        EXECUTE format('COMMENT ON ROLE agent_app IS %L', role_binding);
    ELSIF role_record.rolsuper
       OR role_record.rolinherit
       OR role_record.rolcreaterole
       OR role_record.rolcreatedb
       OR role_record.rolcanlogin
       OR role_record.rolreplication
       OR role_record.rolbypassrls THEN
        RAISE EXCEPTION 'existing agent_app role violates the bootstrap role profile';
    END IF;

    SELECT shobj_description(oid, 'pg_authid')
      INTO existing_binding
      FROM pg_roles
     WHERE rolname = 'agent_app';
    IF existing_binding IS DISTINCT FROM role_binding THEN
        RAISE EXCEPTION
            'agent_app is bound to %, not database %',
            coalesce(existing_binding, '<unbound>'),
            current_database();
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_auth_members AS membership
          JOIN pg_roles AS member_role ON member_role.oid = membership.member
         WHERE member_role.rolname IN ('agent_migrator', 'agent_app')
    ) THEN
        RAISE EXCEPTION 'agent database roles must not inherit or SET ROLE to another role';
    END IF;

    EXECUTE format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format(
        'REVOKE ALL PRIVILEGES ON DATABASE %I FROM agent_migrator, agent_app',
        current_database()
    );
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO agent_migrator, agent_app',
        current_database()
    );
END
$bootstrap_roles$;
-- +goose StatementEnd

REVOKE CREATE ON SCHEMA public FROM PUBLIC, agent_migrator, agent_app;

CREATE SCHEMA agent AUTHORIZATION agent_migrator;
REVOKE ALL ON SCHEMA agent FROM PUBLIC;
GRANT USAGE ON SCHEMA agent TO agent_app;

CREATE TABLE agent.tenants (
    tenant_id varchar(200) PRIMARY KEY,
    display_name varchar(200) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT tenants_tenant_id_not_blank CHECK (tenant_id <> ''),
    CONSTRAINT tenants_display_name_not_blank CHECK (display_name <> '')
);
ALTER TABLE agent.tenants OWNER TO agent_migrator;

CREATE TABLE agent.client_applications (
    tenant_id varchar(200) NOT NULL,
    client_app_id varchar(200) NOT NULL,
    display_name varchar(200) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT client_applications_pk PRIMARY KEY (tenant_id, client_app_id),
    CONSTRAINT client_applications_tenant_fk
        FOREIGN KEY (tenant_id)
        REFERENCES agent.tenants (tenant_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    CONSTRAINT client_applications_tenant_id_not_blank CHECK (tenant_id <> ''),
    CONSTRAINT client_applications_client_app_id_not_blank CHECK (client_app_id <> ''),
    CONSTRAINT client_applications_display_name_not_blank CHECK (display_name <> '')
);
ALTER TABLE agent.client_applications OWNER TO agent_migrator;

ALTER TABLE agent.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenants_tenant_isolation ON agent.tenants
    FOR ALL
    TO agent_app
    USING (
        tenant_id = CASE
            WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
            THEN current_setting('agent.tenant_id', true)
            ELSE NULL
        END
    )
    WITH CHECK (
        tenant_id = CASE
            WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
            THEN current_setting('agent.tenant_id', true)
            ELSE NULL
        END
    );

ALTER TABLE agent.client_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.client_applications FORCE ROW LEVEL SECURITY;
CREATE POLICY client_applications_tenant_isolation ON agent.client_applications
    FOR ALL
    TO agent_app
    USING (
        tenant_id = CASE
            WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
            THEN current_setting('agent.tenant_id', true)
            ELSE NULL
        END
    )
    WITH CHECK (
        tenant_id = CASE
            WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
            THEN current_setting('agent.tenant_id', true)
            ELSE NULL
        END
    );

GRANT SELECT, INSERT ON TABLE
    agent.tenants,
    agent.client_applications
TO agent_app;

ALTER TABLE public.goose_db_version OWNER TO agent_migrator;
REVOKE ALL ON TABLE public.goose_db_version FROM PUBLIC, agent_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.goose_db_version TO agent_migrator;
REVOKE ALL ON SEQUENCE public.goose_db_version_id_seq FROM PUBLIC, agent_app;
GRANT USAGE, SELECT, UPDATE ON SEQUENCE public.goose_db_version_id_seq TO agent_migrator;

-- +goose Down
-- This bootstrap changes database and cluster role ownership. Destructive rollback is
-- deliberately refused; recovery is a reviewed forward migration.
-- +goose StatementBegin
DO $forward_only$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = '0A000',
        MESSAGE = '00001_agent_bootstrap is forward-only; create a reviewed forward migration';
END
$forward_only$;
-- +goose StatementEnd
