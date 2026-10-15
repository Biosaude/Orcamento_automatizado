-- Aplicação MANUAL autorizada, via conexão administrativa DIRETA.
-- Sem credenciais. Não executar pelo startup ou Alembic.
-- Snapshot de roles/ACLs/policies e backup revisados são pré-requisitos.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $guard$
BEGIN
    IF (SELECT count(*) FROM public.alembic_version) <> 1
       OR NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num = '8c41e2f67b90') THEN
        RAISE EXCEPTION 'Revisão Alembic inesperada; abortado';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'biosaude_app') THEN
        CREATE ROLE biosaude_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOINHERIT NOREPLICATION NOBYPASSRLS;
        -- Role nova não tem senha. Configurá-la separadamente por canal seguro.
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'biosaude_app'
        AND (NOT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR rolinherit)
    ) OR EXISTS (
        SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
        WHERE r.rolname = 'biosaude_app'
    ) OR EXISTS (
        SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid
        WHERE r.rolname = 'biosaude_app'
        AND m.member <> (SELECT oid FROM pg_roles WHERE rolname = current_user)
    ) THEN
        RAISE EXCEPTION 'Role operacional NOLOGIN, privilegiada ou com memberships; revisar antes de continuar';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_shdepend d JOIN pg_roles r ON r.oid = d.refobjid
        WHERE d.refclassid = 'pg_authid'::regclass AND d.deptype = 'o'
        AND r.rolname = 'biosaude_app'
    ) THEN
        RAISE EXCEPTION 'Role operacional proprietária de objetos; abortado';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public'
        AND tablename IN ('companies','users','hospitals','products','quote_requests','quote_items')
        AND (tablename, policyname) NOT IN (
            ('users','biosaude_users_read'), ('companies','biosaude_companies_read'),
            ('hospitals','biosaude_catalog_read'), ('hospitals','biosaude_catalog_insert'),
            ('hospitals','biosaude_catalog_update'), ('products','biosaude_catalog_read'),
            ('products','biosaude_catalog_insert'), ('products','biosaude_catalog_update'))
    ) THEN
        RAISE EXCEPTION 'Policies externas exigem conciliação manual; abortado';
    END IF;
    -- Somente o banco conectado é alterado. CONNECT de PUBLIC é removido: revisar
    -- outros consumidores e seus grants explícitos antes de aplicar.
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC, biosaude_app', current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO biosaude_app', current_database());
END
$guard$;

REVOKE ALL ON SCHEMA public FROM PUBLIC, biosaude_app;
GRANT USAGE ON SCHEMA public TO biosaude_app;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, biosaude_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, biosaude_app;
DO $columns$
DECLARE relation record; columns_list text;
BEGIN
    FOR relation IN SELECT c.oid, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f') LOOP
        SELECT string_agg(format('%I', attname), ',') INTO columns_list
            FROM pg_attribute WHERE attrelid = relation.oid AND attnum > 0 AND NOT attisdropped;
        IF columns_list IS NOT NULL THEN
            EXECUTE format('REVOKE ALL PRIVILEGES (%s) ON TABLE public.%I FROM PUBLIC, biosaude_app', columns_list, relation.relname);
        END IF;
    END LOOP;
END
$columns$;
-- UUIDs são gerados pelo backend; nenhuma sequence é necessária.
-- Não conceder leitura de alembic_version nem acesso ao domínio de orçamentos.
GRANT SELECT ON public.companies, public.users, public.hospitals, public.products TO biosaude_app;
GRANT INSERT (id, company_id, name, quote_template, official_table_id) ON public.hospitals TO biosaude_app;
GRANT UPDATE (name, quote_template, official_table_id) ON public.hospitals TO biosaude_app;
GRANT INSERT (id, company_id, code, name, manufacturer) ON public.products TO biosaude_app;
GRANT UPDATE (code, name, manufacturer) ON public.products TO biosaude_app;

DO $access$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE has_schema_privilege('biosaude_app', oid, 'CREATE'))
       OR EXISTS (SELECT 1 FROM pg_class WHERE CASE WHEN relkind = 'S'
           THEN has_sequence_privilege('biosaude_app', oid, 'USAGE,SELECT,UPDATE') ELSE false END)
       OR EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
           WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema')
           AND has_function_privilege('biosaude_app', p.oid, 'EXECUTE'))
       OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname NOT IN ('pg_catalog','information_schema')
           AND n.nspname NOT LIKE 'pg_toast%' AND n.nspname NOT LIKE 'pg_temp_%'
           AND c.relkind IN ('r','p','v','m','f')
           AND NOT (n.nspname = 'public' AND c.relname IN ('companies','users','hospitals','products'))
           AND CASE WHEN c.relkind IN ('r','p','v','m','f') THEN
                (has_table_privilege('biosaude_app', c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR has_any_column_privilege('biosaude_app', c.oid, 'SELECT,INSERT,UPDATE,REFERENCES'))
                ELSE false END) THEN
        RAISE EXCEPTION 'Acesso residual por schemas, funções SECURITY DEFINER ou outras tabelas; abortado';
    END IF;
END
$access$;

-- Não remover policies desconhecidas. As próprias policies são recriadas para
-- permitir reaplicação atômica do mesmo contrato, sem ampliar grants.
DROP POLICY IF EXISTS biosaude_users_read ON public.users;
CREATE POLICY biosaude_users_read ON public.users FOR SELECT TO biosaude_app
    USING (identity_subject = nullif(current_setting('biosaude.subject', true), ''));
DROP POLICY IF EXISTS biosaude_companies_read ON public.companies;
CREATE POLICY biosaude_companies_read ON public.companies FOR SELECT TO biosaude_app
    USING (active AND EXISTS (
        SELECT 1 FROM public.users u WHERE u.company_id = companies.id
        AND u.identity_subject = nullif(current_setting('biosaude.subject', true), '')
        AND u.role IN ('administrator','operator','reviewer')
    ));

DO $policies$
DECLARE
    relation text;
    readable text := $predicate$
        company_id::text = nullif(current_setting('biosaude.company_id', true), '')
        AND EXISTS (SELECT 1 FROM public.users u JOIN public.companies c ON c.id = u.company_id
            WHERE u.company_id = %1$I.company_id AND c.active
            AND u.identity_subject = nullif(current_setting('biosaude.subject', true), '')
            AND u.role IN ('administrator','operator','reviewer'))
    $predicate$;
    writable text := $predicate$
        company_id::text = nullif(current_setting('biosaude.company_id', true), '')
        AND EXISTS (SELECT 1 FROM public.users u JOIN public.companies c ON c.id = u.company_id
            WHERE u.company_id = %1$I.company_id AND c.active
            AND u.identity_subject = nullif(current_setting('biosaude.subject', true), '')
            AND u.role IN ('administrator','operator'))
    $predicate$;
BEGIN
    FOREACH relation IN ARRAY ARRAY['hospitals','products'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS biosaude_catalog_read ON public.%I', relation);
        EXECUTE format('DROP POLICY IF EXISTS biosaude_catalog_insert ON public.%I', relation);
        EXECUTE format('DROP POLICY IF EXISTS biosaude_catalog_update ON public.%I', relation);
        EXECUTE format('CREATE POLICY biosaude_catalog_read ON public.%I FOR SELECT TO biosaude_app USING (%s)', relation, format(readable, relation));
        EXECUTE format('CREATE POLICY biosaude_catalog_insert ON public.%I FOR INSERT TO biosaude_app WITH CHECK (%s)', relation, format(writable, relation));
        EXECUTE format('CREATE POLICY biosaude_catalog_update ON public.%I FOR UPDATE TO biosaude_app USING (%s) WITH CHECK (%s)', relation, format(writable, relation), format(writable, relation));
    END LOOP;
    FOREACH relation IN ARRAY ARRAY['companies','users','hospitals','products','quote_requests','quote_items'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', relation);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', relation);
    END LOOP;
    -- quote_requests/items: sem grants e sem policies => deny all para a app.
END
$policies$;

-- Defaults do executor administrativo para objetos FUTUROS neste banco.
-- REVOKE por schema não remove grants globais (incluindo EXECUTE padrão de PUBLIC).
-- Outros criadores e outros schemas exigem auditoria própria.
ALTER DEFAULT PRIVILEGES REVOKE ALL ON TABLES FROM PUBLIC, biosaude_app;
ALTER DEFAULT PRIVILEGES REVOKE ALL ON SEQUENCES FROM PUBLIC, biosaude_app;
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, biosaude_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC, biosaude_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC, biosaude_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, biosaude_app;
COMMIT;
