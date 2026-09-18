from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class ParticipantStatus(str, Enum):
    pending = "pending"  # присоединился к сессии, но ещё не подтвердил оплату
    paid = "paid"        # сам нажал "Я оплатил"


class PaymentSession(SQLModel, table=True):
    """Один запрос организатора: 'скиньтесь на N голов'."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organizer_id: Optional[int] = None    # user_id организатора из initData, если известен
    chat_id: Optional[int] = None         # id группового чата, если известен
    title: str
    total_amount: float
    head_count: int
    requisites: str                       # текст: номер телефона + банк для СБП
    token: str = Field(index=True, unique=True)  # payload диплинка (?startapp=...)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Participant(SQLModel, table=True):
    """Человек, перешедший по ссылке и привязанный к сессии."""

    __table_args__ = (UniqueConstraint("session_id", "user_id", name="uq_session_user"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="paymentsession.id")
    user_id: int
    first_name: Optional[str] = None
    share_amount: float
    status: ParticipantStatus = Field(default=ParticipantStatus.pending)
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_at: Optional[datetime] = None


class BotUser(SQLModel, table=True):
    """
    Кто уже открывал диалог с ботом (событие bot_started).
    Бот не может написать первым — только этим людям.
    """

    user_id: int = Field(primary_key=True)
    chat_with_bot_id: int
    started_at: datetime = Field(default_factory=datetime.utcnow)
