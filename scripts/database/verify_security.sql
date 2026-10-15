-- SOMENTE LEITURA. Executar após aplicação autorizada, com administrador e app.
SELECT current_database() AS database_name, session_user, current_user;
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication,
       rolbypassrls, rolinherit
FROM pg_roles WHERE rolname = 'biosaude_app';
SELECT parent.rolname AS granted_role, child.rolname AS member
FROM pg_auth_members m JOIN pg_roles parent ON parent.oid = m.roleid
JOIN pg_roles child ON child.oid = m.member
WHERE parent.rolname = 'biosaude_app' OR child.rolname = 'biosaude_app';

SELECT n.nspname, c.relname, owner.rolname AS owner,
       c.relrowsecurity AS rls, c.relforcerowsecurity AS force_rls,
       has_table_privilege('biosaude_app', c.oid, 'SELECT') AS app_select,
       has_table_privilege('biosaude_app', c.oid, 'DELETE') AS app_delete,
       has_table_privilege('biosaude_app', c.oid, 'TRUNCATE') AS app_truncate
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_roles owner ON owner.oid = c.relowner
WHERE n.nspname = 'public' AND c.relkind IN ('r','p') ORDER BY c.relname;

SELECT table_name, column_name, privilege_type, grantee, is_grantable
FROM information_schema.column_privileges
WHERE table_schema = 'public' AND grantee IN ('PUBLIC','biosaude_app')
ORDER BY table_name, column_name, privilege_type;
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies WHERE schemaname = 'public' ORDER BY tablename, policyname;
SELECT n.nspname, has_schema_privilege('biosaude_app', n.oid, 'CREATE') AS app_create
FROM pg_namespace n WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';
SELECT has_database_privilege('biosaude_app', current_database(), 'CONNECT') AS app_connect,
       has_database_privilege('biosaude_app', current_database(), 'CREATE') AS app_create_schema,
       has_database_privilege('biosaude_app', current_database(), 'TEMP') AS app_temp;

-- Rever defaults de CADA role criadora, não apenas os do executor do script.
SELECT owner.rolname, n.nspname, d.defaclobjtype, d.defaclacl
FROM pg_default_acl d JOIN pg_roles owner ON owner.oid = d.defaclrole
LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace;
SELECT n.nspname, p.proname,
       has_function_privilege('biosaude_app', p.oid, 'EXECUTE') AS app_execute
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema');
