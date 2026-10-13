"""HTTP real via ASGI, JWTs assinados e SQLAlchemy em banco sintético isolado."""

import io
import json
import os
from time import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import Settings
from backend.app.core.database import Database
from backend.app.main import create_app
from backend.app.persistence.base import Base
from backend.app.persistence.models import CompanyORM, HospitalORM, ProductORM, UserORM

ISSUER = "https://synthetic-auth.supabase.co/auth/v1"


@pytest.fixture
def catalog(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update(kid="synthetic-signing-key", use="sig", alg="ES256")
    fetched_urls = []

    def jwks_response(request, **kwargs):
        fetched_urls.append(request.full_url)
        assert request.full_url == ISSUER + "/.well-known/jwks.json"
        return io.BytesIO(json.dumps({"keys": [public_jwk]}).encode())

    monkeypatch.setattr("jwt.jwks_client.urllib.request.urlopen", jwks_response)
    test_url = os.environ.get("BIOSAUDE_TEST_DATABASE_URL")
    if test_url:
        parsed = make_url(test_url)
        # Nunca aceitar destinos de produção nesta fixture que cria dados sintéticos.
        assert parsed.host in {"localhost", "127.0.0.1"}
        assert parsed.database == "biosaude_synthetic_tests"
        database = Database(
            Settings(
                _env_file=None,
                database_url=test_url,
                database_ssl_root_cert=os.environ["BIOSAUDE_TEST_DATABASE_CA"],
            )
        )
        engine = database.engine
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    Base.metadata.create_all(
        engine,
        tables=[
            CompanyORM.__table__,
            UserORM.__table__,
            HospitalORM.__table__,
            ProductORM.__table__,
        ],
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    company_a, company_b, inactive_company = uuid4(), uuid4(), uuid4()
    subjects = {
        role: str(uuid4())
        for role in (
            "operator",
            "reviewer",
            "administrator",
            "other",
            "inactive",
            "unknown",
            "ambiguous",
        )
    }
    with sessions() as session:
        session.add_all(
            [
                CompanyORM(id=company_a, name="Synthetic A", active=True),
                CompanyORM(id=company_b, name="Synthetic B", active=True),
                CompanyORM(id=inactive_company, name="Synthetic inactive", active=False),
            ]
        )
        for role in ("operator", "reviewer", "administrator"):
            session.add(
                UserORM(
                    company_id=company_a,
                    identity_subject=subjects[role],
                    display_name="Synthetic user",
                    role=role,
                )
            )
        session.add_all(
            [
                UserORM(
                    company_id=company_b,
                    identity_subject=subjects["other"],
                    display_name="Synthetic B user",
                    role="operator",
                ),
                UserORM(
                    company_id=inactive_company,
                    identity_subject=subjects["inactive"],
                    display_name="Synthetic inactive user",
                    role="administrator",
                ),
                UserORM(
                    company_id=company_a,
                    identity_subject=subjects["unknown"],
                    display_name="Synthetic unknown role",
                    role="superuser",
                ),
                UserORM(
                    company_id=company_a,
                    identity_subject=subjects["ambiguous"],
                    display_name="Synthetic multi-company",
                    role="reviewer",
                ),
                UserORM(
                    company_id=company_b,
                    identity_subject=subjects["ambiguous"],
                    display_name="Synthetic multi-company",
                    role="operator",
                ),
            ]
        )
        session.commit()

    def token(subject=None, signing_key=None, **overrides):
        claims = {
            "sub": subject or subjects["operator"],
            "iss": ISSUER,
            "aud": "authenticated",
            "role": "authenticated",
            "iat": int(time()),
            "exp": int(time()) + 300,
        }
        claims.update(overrides)
        return jwt.encode(
            claims,
            signing_key or private_key,
            algorithm="ES256",
            headers={"kid": "synthetic-signing-key"},
        )

    def headers(role="operator", **claims):
        return {"Authorization": "Bearer " + token(subjects[role], **claims)}

    app = create_app(Settings(_env_file=None, supabase_url=ISSUER.removesuffix("/auth/v1")))
    with TestClient(app) as client:
        client.app.state.database.engine = engine
        client.app.state.database.sessions = sessions
        yield client, headers, token, sessions, company_a, company_b, subjects, fetched_urls
    engine.dispose()


@pytest.mark.parametrize("path", ["/auth/me", "/hospitals", "/products"])
def test_missing_authentication_denies_access(catalog, path):
    client, *_ = catalog
    response = client.get("/api/v1" + path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": int(time()) - 60},
        {"iat": int(time()) + 3600},
        {"iss": "https://untrusted.example.invalid/auth/v1"},
        {"aud": "service_role"},
        {"role": "service_role"},
        {"sub": "invalid-subject"},
        {"nbf": int(time()) + 3600},
    ],
)
def test_invalid_claims_are_rejected(catalog, claims):
    client, _, token, *_ = catalog
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer " + token(**claims)}
        ).status_code
        == 401
    )


def test_forged_signature_and_unsigned_token_are_rejected(catalog):
    client, _, token, *_ = catalog
    forged = token(signing_key=ec.generate_private_key(ec.SECP256R1()))
    for invalid in (
        forged,
        "malformed",
        jwt.encode({"sub": str(uuid4())}, key="", algorithm="none"),
        "x" * 8193,
    ):
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + invalid})
        assert response.status_code == 401
        assert invalid not in response.text


def test_missing_required_claim_is_rejected(catalog):
    client, _, token, *_ = catalog
    # PyJWT requires expiration even when another claim is valid.
    invalid = token(exp=None)
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + invalid}).status_code
        == 401
    )


@pytest.mark.parametrize("role", ["inactive", "unknown"])
def test_inactive_company_and_unknown_role_denied(catalog, role):
    client, headers, *_ = catalog
    assert client.get("/api/v1/auth/me", headers=headers(role)).status_code == 403


def test_unregistered_subject_is_denied(catalog):
    client, _, token, *_ = catalog
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer " + token(str(uuid4()))}
        ).status_code
        == 403
    )


def test_company_and_role_come_from_database_not_claims(catalog):
    client, headers, _, _, company_a, company_b, *_ = catalog
    response = client.get(
        "/api/v1/auth/me",
        headers=headers(
            "reviewer", company_id=str(company_b), app_metadata={"role": "administrator"}
        ),
    )
    assert response.status_code == 200
    assert response.json()["company_id"] == str(company_a)
    assert response.json()["role"] == "reviewer"
    assert "Authorization" not in response.text


def test_multi_company_selection_requires_authorized_membership(catalog):
    client, headers, _, _, company_a, company_b, *_ = catalog
    assert client.get("/api/v1/auth/me", headers=headers("ambiguous")).status_code == 403
    for company, role in ((company_a, "reviewer"), (company_b, "operator")):
        response = client.get(
            "/api/v1/auth/me", headers={**headers("ambiguous"), "X-Company-ID": str(company)}
        )
        assert response.status_code == 200
        assert response.json()["role"] == role
    assert (
        client.get(
            "/api/v1/auth/me", headers={**headers(), "X-Company-ID": str(company_b)}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "resource,payload",
    [
        ("hospitals", {"name": "Synthetic hospital"}),
        ("products", {"code": "SYN-001", "name": "Synthetic product"}),
    ],
)
def test_create_read_list_update_and_cross_company_isolation(catalog, resource, payload):
    client, headers, _, sessions, company_a, company_b, *_ = catalog
    path = "/api/v1/" + resource
    response = client.post(path, headers=headers(), json=payload)
    assert response.status_code == 201
    entity_id = response.json()["id"]
    assert response.json()["company_id"] == str(company_a)
    assert client.get(path, headers=headers()).json()[0]["id"] == entity_id
    assert client.get(path, headers=headers("other")).json() == []
    assert client.get(path + "/" + entity_id, headers=headers("other")).status_code == 404
    updated = {**payload, "name": "Synthetic updated"}
    assert (
        client.put(path + "/" + entity_id, headers=headers("other"), json=updated).status_code
        == 404
    )
    assert client.get(path + "/" + entity_id, headers=headers()).json()["name"] == payload["name"]
    assert client.put(path + "/" + entity_id, headers=headers(), json=updated).status_code == 200
    assert (
        client.get(path + "/" + entity_id, headers=headers("reviewer")).json()["name"]
        == updated["name"]
    )
    # Mesma identidade comercial em outra empresa é permitida e permanece isolada.
    other = client.post(path, headers=headers("other"), json=payload)
    assert other.status_code == 201
    assert other.json()["company_id"] == str(company_b)
    assert client.put(path + "/" + entity_id, headers=headers(), json=updated).status_code == 200
    with sessions() as session:
        model = HospitalORM if resource == "hospitals" else ProductORM
        assert (
            len(
                session.scalars(
                    select(model).where(model.company_id.in_([company_a, company_b]))
                ).all()
            )
            == 2
        )


@pytest.mark.parametrize(
    "resource,payload",
    [
        ("hospitals", {"name": "Synthetic duplicate"}),
        ("products", {"code": "SYN-DUP", "name": "Synthetic product"}),
    ],
)
def test_duplicates_create_and_update_return_conflict(catalog, resource, payload):
    client, headers, *_ = catalog
    path = "/api/v1/" + resource
    assert client.post(path, headers=headers(), json=payload).status_code == 201
    case_duplicate = {k: "  " + v.lower() + "  " for k, v in payload.items()}
    assert client.post(path, headers=headers(), json=case_duplicate).status_code == 409
    different = {
        **payload,
        "name": "Synthetic different",
        **({"code": "SYN-DIFF"} if resource == "products" else {}),
    }
    created = client.post(path, headers=headers(), json=different)
    assert created.status_code == 201
    entity_id = created.json()["id"]
    assert client.put(path + "/" + entity_id, headers=headers(), json=payload).status_code == 409
    assert client.get(path + "/" + entity_id, headers=headers()).json()["name"] == different["name"]


@pytest.mark.parametrize(
    "resource,payload",
    [
        ("hospitals", {"name": "Synthetic hospital"}),
        ("products", {"code": "SYN-001", "name": "Synthetic product"}),
    ],
)
def test_reader_cannot_write_and_administrator_can(catalog, resource, payload):
    client, headers, *_ = catalog
    path = "/api/v1/" + resource
    assert client.post(path, headers=headers("reviewer"), json=payload).status_code == 403
    created = client.post(path, headers=headers("administrator"), json=payload)
    assert created.status_code == 201
    entity_id = created.json()["id"]
    assert (
        client.put(path + "/" + entity_id, headers=headers("reviewer"), json=payload).status_code
        == 403
    )


@pytest.mark.parametrize(
    "resource,payload",
    [
        ("hospitals", {"name": "   "}),
        ("hospitals", {"name": "x" * 256}),
        ("hospitals", {"name": "Synthetic", "quote_template": "unknown"}),
        ("hospitals", {"name": "Synthetic", "quote_template": "sao_camilo"}),
        ("hospitals", {"name": "Synthetic", "company_id": str(uuid4())}),
        ("products", {"code": "", "name": "Synthetic"}),
        ("products", {"code": "x" * 101, "name": "Synthetic"}),
        ("products", {"code": "SYN", "name": "Synthetic", "company_id": str(uuid4())}),
        ("products", {"code": "SYN", "name": "Synthetic", "id": str(uuid4())}),
    ],
)
def test_invalid_payloads_and_scope_injection_denied(catalog, resource, payload):
    client, headers, *_ = catalog
    assert client.post("/api/v1/" + resource, headers=headers(), json=payload).status_code == 422


def test_pagination_invalid_identifiers_and_official_template(catalog):
    client, headers, *_ = catalog
    assert client.get("/api/v1/products?limit=101", headers=headers()).status_code == 422
    assert client.get("/api/v1/hospitals?offset=-1", headers=headers()).status_code == 422
    assert client.get("/api/v1/hospitals/not-a-uuid", headers=headers()).status_code == 422
    assert client.get("/api/v1/products/" + str(uuid4()), headers=headers()).status_code == 404
    response = client.post(
        "/api/v1/hospitals",
        headers=headers(),
        json={
            "name": "Synthetic exception",
            "quote_template": "sao_camilo",
            "official_table_id": "synthetic-official-table",
        },
    )
    assert response.status_code == 201


def test_jwks_destination_is_fixed_and_cached(catalog):
    client, headers, _, _, _, _, _, fetched = catalog
    for _ in range(2):
        assert client.get("/api/v1/auth/me", headers=headers()).status_code == 200
    assert fetched == [ISSUER + "/.well-known/jwks.json"]


def test_unconfigured_auth_fails_closed():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/api/v1/products").status_code == 401
        assert (
            client.get(
                "/api/v1/products", headers={"Authorization": "Bearer synthetic-token"}
            ).status_code
            == 503
        )
        assert client.get("/health").status_code == 200


def test_missing_and_invalid_authentication_never_open_database_session(catalog):
    from unittest.mock import MagicMock

    client, *_ = catalog
    sessions = MagicMock()
    client.app.state.database.sessions = sessions
    for headers in ({}, {"Authorization": "Bearer malformed"}):
        assert client.get("/api/v1/products", headers=headers).status_code == 401
    sessions.assert_not_called()


def test_jwks_connectivity_failure_is_generic_and_fails_closed(catalog, monkeypatch):
    from jwt import PyJWKClientConnectionError

    client, headers, *_ = catalog

    def unavailable(*args, **kwargs):
        raise PyJWKClientConnectionError("synthetic-sensitive-provider-error")

    monkeypatch.setattr(
        client.app.state.token_verifier.jwks, "get_signing_key_from_jwt", unavailable
    )
    response = client.get("/api/v1/products", headers=headers())
    assert response.status_code == 503
    assert "synthetic-sensitive" not in response.text


def test_database_failures_are_generic_and_transactions_roll_back(catalog, monkeypatch):
    from sqlalchemy.exc import IntegrityError, OperationalError

    client, headers, _, sessions, *_ = catalog

    def conflict(self):
        raise IntegrityError("synthetic-sensitive-query", {}, Exception("synthetic-secret"))

    monkeypatch.setattr(sessions.class_, "commit", conflict)
    response = client.post(
        "/api/v1/products", headers=headers(), json={"code": "SYN-FAIL", "name": "Synthetic"}
    )
    assert response.status_code == 409
    assert "synthetic" not in response.text
    assert client.get("/api/v1/products", headers=headers()).json() == []

    def unavailable(self, *args, **kwargs):
        raise OperationalError("synthetic-sensitive-query", {}, Exception("synthetic-secret"))

    monkeypatch.setattr(sessions.class_, "scalars", unavailable)
    response = client.get("/api/v1/products", headers=headers())
    assert response.status_code == 503
    assert "synthetic" not in response.text


@pytest.mark.skipif(
    not os.environ.get("BIOSAUDE_TEST_DATABASE_URL"),
    reason="Requer PostgreSQL sintético local com TLS",
)
@pytest.mark.parametrize(
    "resource,payload",
    [
        ("hospitals", {"name": "Synthetic concurrent hospital"}),
        ("products", {"code": "SYN-CONCURRENT", "name": "Synthetic concurrent product"}),
    ],
)
def test_postgresql_serializes_concurrent_duplicate_creation(catalog, resource, payload):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    client, headers, *_ = catalog
    barrier = Barrier(2)

    def create():
        barrier.wait(timeout=5)
        return client.post("/api/v1/" + resource, headers=headers(), json=payload).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))
    assert sorted(results) == [201, 409]
    assert len(client.get("/api/v1/" + resource, headers=headers()).json()) == 1


def test_permission_change_and_membership_removal_take_effect_with_existing_token(catalog):
    client, headers, _, sessions, _, _, subjects, _ = catalog
    authenticated = headers()
    assert client.get("/api/v1/auth/me", headers=authenticated).status_code == 200
    with sessions() as session:
        user = session.scalar(
            select(UserORM).where(UserORM.identity_subject == subjects["operator"])
        )
        user.role = "reviewer"
        session.commit()
    assert (
        client.post(
            "/api/v1/hospitals", headers=authenticated, json={"name": "Synthetic denied"}
        ).status_code
        == 403
    )
    with sessions() as session:
        user = session.scalar(
            select(UserORM).where(UserORM.identity_subject == subjects["operator"])
        )
        session.delete(user)
        session.commit()
    assert client.get("/api/v1/auth/me", headers=authenticated).status_code == 403


def test_hmac_tokens_are_rejected_before_jwks_access(catalog):
    client, _, _, _, _, _, subjects, fetched = catalog
    token = jwt.encode(
        {"sub": subjects["operator"], "iss": ISSUER},
        "synthetic-test-secret",
        algorithm="HS256",
        headers={"kid": "synthetic-signing-key"},
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )
    assert fetched == []


def test_rsa_signed_tokens_are_verified(catalog, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa

    client, _, _, _, _, _, subjects, _ = catalog
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update(kid="synthetic-rsa-key", use="sig", alg="RS256")
    monkeypatch.setattr(
        client.app.state.token_verifier.jwks, "fetch_data", lambda: {"keys": [public_jwk]}
    )
    token = jwt.encode(
        {
            "sub": subjects["operator"],
            "iss": ISSUER,
            "aud": "authenticated",
            "role": "authenticated",
            "iat": int(time()),
            "exp": int(time()) + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "synthetic-rsa-key"},
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code
        == 200
    )
