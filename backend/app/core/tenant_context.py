"""Contexto SQL transacional derivado exclusivamente da identidade verificada."""

from sqlalchemy import event, text
from sqlalchemy.orm import Session

_CONTEXT = "biosaude_tenant_context"


def _apply(connection, subject: str, company: str) -> None:
    connection.execute(
        text(
            "SELECT set_config('biosaude.subject', :subject, true), "
            "set_config('biosaude.company_id', :company, true)"
        ),
        {"subject": subject, "company": company},
    ).close()


@event.listens_for(Session, "after_begin")
def _restore_context(session, transaction, connection):
    context = session.info.get(_CONTEXT)
    if context is not None and connection.dialect.name == "postgresql":
        _apply(connection, *context)


def bind_context(session: Session, subject: str, company: str = "") -> None:
    """SET LOCAL, reaplicado em cada transação, inclusive após commit/rollback.

    Não valida JWT: o chamador deve receber subject do verificador confiável e
    company de um vínculo autorizado. Não aceita esses valores de payload/claims.
    """
    session.info[_CONTEXT] = (subject, company)
    if session.in_transaction():
        connection = session.connection()
        if connection.dialect.name == "postgresql":
            _apply(connection, subject, company)
