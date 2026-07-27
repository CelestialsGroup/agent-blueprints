-- Test-only migration proving that goose can operate through a distinct Login
-- while DDL ownership remains with the database-bound Migrator group role.
-- +goose Up
SET ROLE agent_migrator;
CREATE TABLE agent.migrator_role_probe (
    probe_id bigint PRIMARY KEY
);
RESET ROLE;

-- +goose Down
SET ROLE agent_migrator;
DROP TABLE agent.migrator_role_probe;
RESET ROLE;
