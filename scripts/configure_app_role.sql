\set ON_ERROR_STOP on

-- Run as the database owner after every migration. Override with:
--   psql ... --set=app_role=vglpos_app -f scripts/configure_app_role.sql
\if :{?app_role}
\else
\set app_role vglpos_app
\endif

SELECT format('CREATE ROLE %I LOGIN NOINHERIT', :'app_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_role')
\gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app_role";

-- Fail closed for new tables: rerun this script after migrations instead of
-- granting broad default privileges that could expose future sensitive tables.
WITH RECURSIVE audit_tree(oid) AS (
    SELECT 'public.audit_log'::regclass::oid
    UNION ALL
    SELECT inheritance.inhrelid
    FROM pg_inherits AS inheritance
    JOIN audit_tree ON inheritance.inhparent = audit_tree.oid
)
SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I.%I TO %I',
    namespace.nspname,
    relation.relname,
    :'app_role'
)
FROM pg_class AS relation
JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
LEFT JOIN audit_tree ON audit_tree.oid = relation.oid
WHERE namespace.nspname = 'public'
  AND relation.relkind IN ('r', 'p')
  AND audit_tree.oid IS NULL
\gexec

WITH RECURSIVE audit_tree(oid) AS (
    SELECT 'public.audit_log'::regclass::oid
    UNION ALL
    SELECT inheritance.inhrelid
    FROM pg_inherits AS inheritance
    JOIN audit_tree ON inheritance.inhparent = audit_tree.oid
)
SELECT format(
    'REVOKE ALL PRIVILEGES ON TABLE %I.%I FROM %I',
    namespace.nspname,
    relation.relname,
    :'app_role'
)
FROM audit_tree
JOIN pg_class AS relation ON relation.oid = audit_tree.oid
JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
\gexec

GRANT SELECT, INSERT ON TABLE public.audit_log TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";

