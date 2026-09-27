from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)

    with engine.begin() as connection:
        payment_columns = {
            column["name"] for column in inspect(connection).get_columns("paymentsession")
        }
        participant_columns = {
            column["name"] for column in inspect(connection).get_columns("participant")
        }

        if "payment_mode" not in payment_columns:
            connection.execute(text(
                "ALTER TABLE paymentsession ADD COLUMN payment_mode VARCHAR(16) NOT NULL DEFAULT 'equal'"
            ))
        if "contribution_amount_cents" not in participant_columns:
            connection.execute(text(
                "ALTER TABLE participant ADD COLUMN contribution_amount_cents INTEGER NOT NULL DEFAULT 0"
            ))
            connection.execute(text(
                "UPDATE participant SET contribution_amount_cents = CAST(ROUND(share_amount * 100) AS INTEGER) "
                "WHERE status = 'paid'"
            ))
        if "remaining_amount_cents" not in payment_columns:
            connection.execute(text(
                "ALTER TABLE paymentsession ADD COLUMN remaining_amount_cents INTEGER NOT NULL DEFAULT 0"
            ))
            connection.execute(text(
                "UPDATE paymentsession SET remaining_amount_cents = "
                "CAST(ROUND(total_amount * 100) AS INTEGER) - COALESCE(("
                "SELECT SUM(participant.contribution_amount_cents) FROM participant "
                "WHERE participant.session_id = paymentsession.id"
                "), 0)"
            ))

        if engine.dialect.name == "postgresql":
            connection.execute(text(
                "ALTER TABLE paymentsession ALTER COLUMN organizer_id DROP NOT NULL"
            ))
            connection.execute(text(
                "ALTER TABLE paymentsession ALTER COLUMN chat_id DROP NOT NULL"
            ))


def get_session():
    with Session(engine) as session:
        yield session
