from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


def init_db() -> None:
    # Безопасное обновление схемы для локального прототипа.
    SQLModel.metadata.create_all(engine)

    # Совместимость с уже существующей Postgres-базой: на ранних версиях колонки были NOT NULL.
    if engine.dialect.name == "postgresql":
        with Session(engine) as session:
            session.exec(text("ALTER TABLE paymentsession ALTER COLUMN organizer_id DROP NOT NULL"))
            session.exec(text("ALTER TABLE paymentsession ALTER COLUMN chat_id DROP NOT NULL"))
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session
