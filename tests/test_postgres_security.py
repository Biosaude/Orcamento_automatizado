"""Prova de privilégios/RLS em PostgreSQL LOCAL descartável, nunca Neon real."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import Error as PsycopgError
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from test_catalog_auth import catalog as catalog

from backend.app.core.config import Settings
from backend.app.core.database import Database
from backend.app.core.tenant_context import bind_context
from backend.app.persistence.base import Base
from backend.app.persistence.models import CompanyORM, HospitalORM, ProductORM, UserORM

pytestmark = pytest.mark.skipif(
    not os.environ.get("BIOSAUDE_SECURITY_TEST_DATABASE_URL"),
    reason="Requer PostgreSQL local sintético para testar roles e RLS reais",
)


@pytest.fixture(scope="module")
def secured():
    url = make_url(os.environ["BIOSAUDE_SECURITY_TEST_DATABASE_URL"])
    assert url.host in {"localhost", "127.0.0.1"}
    assert url.database == "biosaude_synthetic_tests"
    ca = os.environ["BIOSAUDE_TEST_DATABASE_CA"]
    admin = Database(
        Settings(
            _env_file=None,
            database_url=url.render_as_string(hide_password=False),
            database_ssl_root_cert=ca,
        )
    )
    Base.metadata.create_all(admin.engine)
    with admin.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS public.alembic_version "
            "(version_num varchar(32) PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "INSERT INTO public.alembic_version VALUES ('8c41e2f67b90') ON CONFLICT DO NOTHING"
        )

    def apply():
        raw = admin.engine.raw_connection()
        driver = raw.driver_connection
        previous = driver.autocommit
        driver.autocommit = True
        try:
            with driver.cursor() as cursor:
                try:
                    cursor.execute(Path("scripts/database/apply_security.sql").read_text())
                except Exception:
                    cursor.execute("ROLLBACK")
                    raise
        finally:
            driver.autocommit = previous
            raw.close()

    with admin.engine.begin() as connection:
        # Grant legado em COLUNA: REVOKE de tabela sozinho não o removeria.
        connection.exec_driver_sql("GRANT UPDATE (role) ON public.users TO PUBLIC")
    apply()
    apply()  # Reaplicação do mesmo contrato deve ser segura.
    with admin.engine.begin() as connection:
        # Senha SOMENTE sintética, criada no container descartável, nunca produção.
        connection.exec_driver_sql(
            "ALTER ROLE biosaude_app PASSWORD 'synthetic_operational_password'"
        )
    app_url = url.set(username="biosaude_app", password="synthetic_operational_password")
    app = Database(
        Settings(
            _env_file=None,
            database_url=app_url.render_as_string(hide_password=False),
            database_ssl_root_cert=ca,
            database_pool_size=1,
        )
    )
    yield admin, app, apply
    app.dispose()
    admin.dispose()


@pytest.fixture
def tenants(secured):
    admin, app, _ = secured
    company_a, company_b, inactive = uuid4(), uuid4(), uuid4()
    subject_a, subject_b, reviewer, disabled = [str(uuid4()) for _ in range(4)]
    hospital_a, hospital_b = uuid4(), uuid4()
    product_a, product_b = uuid4(), uuid4()
    with sessionmaker(admin.engine)() as session:
        session.add_all(
            [
                CompanyORM(id=company_a, name="Synthetic security A", active=True),
                CompanyORM(id=company_b, name="Synthetic security B", active=True),
                CompanyORM(id=inactive, name="Synthetic inactive", active=False),
            ]
        )
        session.flush()
        session.add_all(
            [
                UserORM(
                    company_id=company_a,
                    display_name="Synthetic A",
                    role="operator",
                    identity_subject=subject_a,
                ),
                UserORM(
                    company_id=company_b,
                    display_name="Synthetic B",
                    role="administrator",
                    identity_subject=subject_b,
                ),
                UserORM(
                    company_id=company_a,
                    display_name="Synthetic reader",
                    role="reviewer",
                    identity_subject=reviewer,
                ),
                UserORM(
                    company_id=inactive,
                    display_name="Synthetic inactive",
                    role="operator",
                    identity_subject=disabled,
                ),
                HospitalORM(id=hospital_a, company_id=company_a, name="Synthetic hospital A"),
                HospitalORM(id=hospital_b, company_id=company_b, name="Synthetic hospital B"),
                ProductORM(
                    id=product_a, company_id=company_a, code="SYN-A", name="Synthetic product A"
                ),
                ProductORM(
                    id=product_b, company_id=company_b, code="SYN-B", name="Synthetic product B"
                ),
            ]
        )
        session.commit()
    sessions = sessionmaker(app.engine, expire_on_commit=False)
    return (
        sessions,
        company_a,
        company_b,
        subject_a,
        subject_b,
        reviewer,
        disabled,
        inactive,
        hospital_a,
        hospital_b,
        product_a,
        product_b,
    )


def test_role_has_minimal_properties_and_no_memberships(secured):
    _, app, _ = secured
    with app.engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, "
                "rolreplication, rolbypassrls, rolinherit FROM pg_roles "
                "WHERE rolname = current_user"
            )
        ).one()
        assert row == ("biosaude_app", False, False, False, False, False, False)
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_auth_members WHERE member = "
                    "(SELECT oid FROM pg_roles WHERE rolname = current_user)"
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='public' AND c.relname IN ('companies','users','hospitals',"
                    "'products','quote_requests','quote_items') "
                    "AND c.relrowsecurity AND c.relforcerowsecurity"
                )
            )
            == 6
        )


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE public.synthetic_forbidden (id int)",
        "CREATE TEMP TABLE synthetic_forbidden (id int)",
        "CREATE SCHEMA synthetic_forbidden",
        "CREATE ROLE synthetic_forbidden",
        "CREATE DATABASE synthetic_forbidden",
        "TRUNCATE public.hospitals",
        "ALTER TABLE public.hospitals DISABLE ROW LEVEL SECURITY",
        "DROP TABLE public.products",
        "SET ROLE synthetic_user",
        "SELECT * FROM public.alembic_version",
        "SELECT * FROM public.quote_requests",
        "SELECT * FROM public.quote_items",
        "UPDATE public.users SET role='administrator'",
        "DELETE FROM public.hospitals",
        "UPDATE public.hospitals SET company_id=gen_random_uuid()",
    ],
)
def test_administrative_and_unimplemented_operations_denied(secured, statement):
    _, app, _ = secured
    with app.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        with pytest.raises(DBAPIError) as error:
            connection.exec_driver_sql(statement)
        assert error.value.orig.sqlstate == "42501"
        connection.rollback()


def test_cannot_grant_privileges_to_itself(secured):
    _, app, _ = secured
    with app.engine.connect() as connection:
        # PostgreSQL pode emitir WARNING e nenhum grant, em vez de exceção.
        try:
            connection.exec_driver_sql("GRANT ALL ON public.products TO biosaude_app")
            connection.commit()
        except DBAPIError:
            connection.rollback()
        assert (
            connection.scalar(
                text("SELECT has_table_privilege(current_user, 'public.products', 'TRUNCATE')")
            )
            is False
        )
        assert (
            connection.scalar(
                text("SELECT has_table_privilege(current_user, 'public.users', 'UPDATE')")
            )
            is False
        )
        assert (
            connection.scalar(
                text(
                    "SELECT has_table_privilege(current_user, 'public.products', "
                    "'SELECT WITH GRANT OPTION')"
                )
            )
            is False
        )


@pytest.mark.parametrize("model", [HospitalORM, ProductORM])
def test_rls_prevents_unfiltered_cross_company_reads_and_updates(tenants, model):
    sessions, company_a, company_b, subject_a, _, *_ = tenants
    with sessions() as session:
        bind_context(session, subject_a, str(company_a))
        # Intencionalmente SEM filtros da API para provar enforcement no banco.
        rows = session.scalars(select(model)).all()
        assert rows and {row.company_id for row in rows} == {company_a}
        result = session.execute(
            text(
                f"UPDATE public.{model.__tablename__} SET name='Synthetic cross denied' "
                "WHERE company_id=:company"
            ),
            {"company": company_b},
        )
        assert result.rowcount == 0
        session.rollback()


@pytest.mark.parametrize("subject_type", ["missing", "invalid", "wrong_company", "inactive"])
def test_invalid_identity_and_tenant_context_fail_closed(tenants, subject_type):
    sessions, company_a, company_b, subject_a, _, _, disabled, inactive, *_ = tenants
    with sessions() as session:
        if subject_type == "invalid":
            bind_context(session, str(uuid4()), str(company_a))
        elif subject_type == "wrong_company":
            bind_context(session, subject_a, str(company_b))
        elif subject_type == "inactive":
            bind_context(session, disabled, str(inactive))
        assert session.scalars(select(HospitalORM)).all() == []
        assert session.scalars(select(ProductORM)).all() == []
        with pytest.raises(DBAPIError) as error:
            session.add(HospitalORM(company_id=company_a, name="Synthetic denied"))
            session.flush()
        assert error.value.orig.sqlstate == "42501"
        session.rollback()


def test_writer_can_insert_update_and_reviewer_cannot_write(tenants):
    sessions, company_a, _, subject_a, _, reviewer, *_ = tenants
    entity = uuid4()
    with sessions() as session:
        bind_context(session, subject_a, str(company_a))
        session.add(
            ProductORM(id=entity, company_id=company_a, code="SYN-NEW", name="Synthetic created")
        )
        session.commit()
        # Nova transação na mesma Session: contexto deve ser reaplicado.
        product = session.scalar(select(ProductORM).where(ProductORM.id == entity))
        assert product.name == "Synthetic created"
        product.name = "Synthetic updated"
        session.commit()
    with sessions() as session:
        bind_context(session, reviewer, str(company_a))
        assert (
            session.scalar(select(ProductORM).where(ProductORM.id == entity)).name
            == "Synthetic updated"
        )
        with pytest.raises(DBAPIError):
            session.add(
                ProductORM(company_id=company_a, code="SYN-READER", name="Synthetic denied")
            )
            session.flush()
        session.rollback()
        result = session.execute(
            text("UPDATE public.products SET name='Synthetic denied' WHERE id=:id"), {"id": entity}
        )
        assert result.rowcount == 0


def test_pool_does_not_leak_context_between_sessions_or_after_rollback(tenants):
    sessions, company_a, company_b, subject_a, subject_b, *_ = tenants
    with sessions() as session:
        bind_context(session, subject_a, str(company_a))
        assert {row.company_id for row in session.scalars(select(ProductORM))} == {company_a}
        session.commit()
    with sessions() as session:
        assert session.scalars(select(ProductORM)).all() == []
    with sessions() as session:
        bind_context(session, subject_b, str(company_b))
        assert {row.company_id for row in session.scalars(select(ProductORM))} == {company_b}
        session.rollback()
        assert {row.company_id for row in session.scalars(select(ProductORM))} == {company_b}
    with sessions() as session:
        assert session.scalars(select(ProductORM)).all() == []


def test_cannot_insert_record_into_another_company(tenants):
    sessions, company_a, company_b, subject_a, *_ = tenants
    with sessions() as session:
        bind_context(session, subject_a, str(company_a))
        with pytest.raises(DBAPIError) as error:
            session.add(HospitalORM(company_id=company_b, name="Synthetic cross denied"))
            session.flush()
        assert error.value.orig.sqlstate == "42501"
        session.rollback()


@pytest.mark.skipif(
    not os.environ.get("BIOSAUDE_TEST_DATABASE_URL"),
    reason="Requer fixture HTTP no mesmo PostgreSQL local",
)
def test_http_api_with_real_nonowner_role_and_rls(secured, request):
    _, app, _ = secured
    client, headers, _, _, company_a, company_b, *_ = request.getfixturevalue("catalog")
    client.app.state.database.sessions = sessionmaker(app.engine, expire_on_commit=False)
    for resource, payload in (
        ("hospitals", {"name": "Synthetic RLS hospital"}),
        ("products", {"name": "Synthetic RLS product", "code": "SYN-RLS"}),
    ):
        path = "/api/v1/" + resource
        assert client.get(path).status_code == 401
        created = client.post(path, headers=headers(), json=payload)
        assert created.status_code == 201
        assert created.json()["company_id"] == str(company_a)
        entity_id = created.json()["id"]
        assert client.get(path, headers=headers("other")).json() == []
        assert client.get(path + "/" + entity_id, headers=headers("other")).status_code == 404
        assert (
            client.put(path + "/" + entity_id, headers=headers("other"), json=payload).status_code
            == 404
        )
        assert (
            client.put(path + "/" + entity_id, headers=headers(), json=payload).status_code == 200
        )
        assert client.post(path, headers=headers("reviewer"), json=payload).status_code == 403
    # Um header só seleciona vínculo real: não autoriza empresa arbitrária.
    assert (
        client.get(
            "/api/v1/auth/me", headers={**headers(), "X-Company-ID": str(company_b)}
        ).status_code
        == 403
    )


def test_provisioning_refuses_privileged_role_without_partial_changes(secured):
    admin, app, apply = secured
    with admin.engine.begin() as connection:
        connection.exec_driver_sql("ALTER ROLE biosaude_app CREATEROLE")
    try:
        with pytest.raises(PsycopgError):
            apply()
    finally:
        with admin.engine.begin() as connection:
            connection.exec_driver_sql("ALTER ROLE biosaude_app NOCREATEROLE")
    assert app.probe()


def test_provisioning_refuses_unknown_policies_instead_of_or_bypass(secured):
    admin, _, apply = secured
    with admin.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE POLICY biosaude_users_read ON public.products "
            "FOR SELECT TO biosaude_app USING (true)"
        )
    try:
        with pytest.raises(PsycopgError):
            apply()
    finally:
        with admin.engine.begin() as connection:
            connection.exec_driver_sql("DROP POLICY biosaude_users_read ON public.products")


def test_provisioning_refuses_public_security_definer_functions(secured):
    admin, _, apply = secured
    with admin.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION public.synthetic_escalation() RETURNS int "
            "LANGUAGE SQL SECURITY DEFINER AS 'SELECT 1'"
        )
        connection.exec_driver_sql(
            "GRANT EXECUTE ON FUNCTION public.synthetic_escalation() TO PUBLIC"
        )
    try:
        with pytest.raises(PsycopgError):
            apply()
    finally:
        with admin.engine.begin() as connection:
            connection.exec_driver_sql("DROP FUNCTION public.synthetic_escalation()")


def test_setting_row_security_off_does_not_bypass_rls(tenants):
    sessions, company_a, _, subject_a, *_ = tenants
    with sessions() as session:
        bind_context(session, subject_a, str(company_a))
        session.execute(text("SET LOCAL row_security = off"))
        with pytest.raises(DBAPIError) as error:
            session.scalars(select(ProductORM)).all()
        assert error.value.orig.sqlstate == "42501"
        session.rollback()


def test_force_rls_also_applies_to_non_superuser_table_owner(secured):
    admin, _, _ = secured
    with admin.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE ROLE synthetic_rls_owner NOLOGIN NOSUPERUSER NOBYPASSRLS"
        )
        connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO synthetic_rls_owner")
        connection.exec_driver_sql("ALTER TABLE public.hospitals OWNER TO synthetic_rls_owner")
    try:
        with admin.engine.connect() as connection:
            connection.exec_driver_sql("SET LOCAL ROLE synthetic_rls_owner")
            # Owner sem BYPASSRLS não está em nenhuma policy autorizada.
            assert connection.execute(text("SELECT * FROM public.hospitals")).all() == []
            connection.rollback()
    finally:
        with admin.engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE public.hospitals OWNER TO synthetic_user")
            connection.exec_driver_sql("REVOKE USAGE ON SCHEMA public FROM synthetic_rls_owner")
            connection.exec_driver_sql("DROP ROLE synthetic_rls_owner")


def test_verification_script_is_usable_by_admin_and_app_in_read_only_transaction(secured):
    admin, app, _ = secured
    for database in (admin, app):
        raw = database.engine.raw_connection()
        try:
            with raw.driver_connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(Path("scripts/database/verify_security.sql").read_text())
                count = 0
                while True:
                    cursor.fetchall()
                    count += 1
                    if not cursor.nextset():
                        break
                assert count >= 8
        finally:
            raw.rollback()
            raw.close()


def test_identity_lookup_only_exposes_own_memberships_before_company_selection(tenants):
    sessions, company_a, _, subject_a, *_ = tenants
    with sessions() as session:
        bind_context(session, subject_a)
        assert {user.identity_subject for user in session.scalars(select(UserORM))} == {subject_a}
        assert {company.id for company in session.scalars(select(CompanyORM))} == {company_a}
        assert session.scalars(select(HospitalORM)).all() == []


def test_future_objects_do_not_gain_automatic_operational_privileges(secured):
    admin, _, _ = secured
    with admin.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION public.synthetic_default_definer() RETURNS int "
            "LANGUAGE SQL SECURITY DEFINER AS 'SELECT 1'"
        )
        connection.exec_driver_sql("CREATE TABLE public.synthetic_future (id int)")
        connection.exec_driver_sql("CREATE SEQUENCE public.synthetic_future_seq")
        try:
            assert (
                connection.scalar(
                    text(
                        "SELECT has_function_privilege('biosaude_app', "
                        "'public.synthetic_default_definer()', 'EXECUTE')"
                    )
                )
                is False
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT has_table_privilege('biosaude_app',"
                        "'public.synthetic_future','SELECT')"
                    )
                )
                is False
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT has_sequence_privilege('biosaude_app',"
                        "'public.synthetic_future_seq','USAGE')"
                    )
                )
                is False
            )
        finally:
            connection.exec_driver_sql("DROP FUNCTION public.synthetic_default_definer()")
            connection.exec_driver_sql("DROP TABLE public.synthetic_future")
            connection.exec_driver_sql("DROP SEQUENCE public.synthetic_future_seq")
