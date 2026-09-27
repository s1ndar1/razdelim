import secrets
import string
import hmac
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional, Union

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlmodel import Session, select

from .bot import send_message
from .config import (
    APP_ENV,
    BOT_NAME,
    BOT_TOKEN,
    DEMO_MODE,
    MAX_INIT_DATA_MAX_AGE_SECONDS,
    MAX_WEBHOOK_SECRET,
)
from .database import engine, get_session, init_db
from .models import BotUser, Participant, ParticipantStatus, PaymentSession
from .schemas import (
    ConfirmRequest,
    JoinRequest,
    JoinResponse,
    ParticipantOut,
    SessionCreate,
    SessionOut,
    SessionStatusOut,
)
from .security import validate_init_data

TOKEN_ALPHABET = string.ascii_letters + string.digits  # допустимые символы payload диплинка
DEMO_ORGANIZER_ID = 90001
DEMO_PARTICIPANT_ID = 90002
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def is_local_demo(request: Request) -> bool:
    client_host = request.client.host if request.client else ""
    return (
        DEMO_MODE
        and APP_ENV == "development"
        and client_host in LOOPBACK_HOSTS
    )


def serialize_session(payment_session: PaymentSession, request: Request) -> SessionOut:
    if is_local_demo(request):
        link = f"{request.base_url}?demo=participant&startapp={payment_session.token}"
    else:
        link = f"https://max.ru/{BOT_NAME}?startapp={payment_session.token}"
    return SessionOut(
        id=payment_session.id,
        title=payment_session.title,
        total_amount=payment_session.total_amount,
        head_count=payment_session.head_count,
        payment_mode=payment_session.payment_mode,
        remaining_amount=payment_session.remaining_amount_cents / 100,
        per_head=round(payment_session.total_amount / payment_session.head_count, 2),
        link=link,
    )


def amount_to_cents(amount: Union[Decimal, float]) -> int:
    return int(
        (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def require_user_id(init_data: Optional[str], request: Request) -> int:
    payload = validate_max_init_data(
        init_data,
        request,
        demo_user_id=DEMO_ORGANIZER_ID,
    )
    user = payload.get("user") if payload else None
    user_id = user.get("id") if isinstance(user, dict) else None
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise HTTPException(401, "Не удалось подтвердить пользователя MAX")
    return user_id


def validate_max_init_data(
    init_data: Optional[str],
    request: Request,
    *,
    demo_user_id: Optional[int] = None,
) -> dict:
    if init_data == "DEMO" and is_local_demo(request):
        return {"user": {"id": demo_user_id or DEMO_ORGANIZER_ID, "first_name": "Демо-участник"}}
    if not BOT_TOKEN:
        raise HTTPException(503, "BOT_TOKEN не настроен")
    payload = validate_init_data(
        init_data,
        BOT_TOKEN,
        max_age_seconds=MAX_INIT_DATA_MAX_AGE_SECONDS,
    )
    if payload is None:
        raise HTTPException(401, "Не удалось подтвердить подлинность initData")
    return payload


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Разделим — прототип", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/status")
def status_page():
    return FileResponse(STATIC_DIR / "status.html")


@app.get("/organizer")
def organizer_page():
    return FileResponse(STATIC_DIR / "organizer.html")


@app.get("/health")
def health_check():
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "db": "unavailable"})


@app.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    request: Request,
    x_max_init_data: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
):
    organizer_id = require_user_id(x_max_init_data, request)
    payment_sessions = session.exec(
        select(PaymentSession)
        .where(PaymentSession.organizer_id == organizer_id)
        .order_by(PaymentSession.id.desc())
    ).all()
    return [serialize_session(item, request) for item in payment_sessions]


@app.get("/sessions/{session_id}", response_model=SessionOut)
def get_session_by_id(
    session_id: int,
    request: Request,
    x_max_init_data: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
):
    organizer_id = require_user_id(x_max_init_data, request)
    payment_session = session.get(PaymentSession, session_id)
    if not payment_session or payment_session.organizer_id != organizer_id:
        raise HTTPException(404, "Сессия не найдена")
    return serialize_session(payment_session, request)


@app.post("/sessions", response_model=SessionOut)
def create_session(
    data: SessionCreate,
    request: Request,
    session: Session = Depends(get_session),
):
    """Организатор создаёт запрос на скидывание. Возвращает диплинк для группы."""
    organizer_id = require_user_id(data.init_data, request)
    if data.head_count < 1:
        raise HTTPException(400, "head_count должен быть не меньше 1")
    total_amount_cents = amount_to_cents(data.total_amount)
    if total_amount_cents <= 0:
        raise HTTPException(400, "total_amount должен быть больше 0")
    if data.payment_mode == "equal" and total_amount_cents < data.head_count:
        raise HTTPException(400, "Для режима «Поровну» сумма должна быть не меньше числа участников")

    token = "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(12))

    payment_session = PaymentSession(
        organizer_id=organizer_id,
        title=data.title,
        total_amount=data.total_amount,
        head_count=data.head_count,
        payment_mode=data.payment_mode,
        remaining_amount_cents=total_amount_cents,
        requisites=data.requisites,
        token=token,
    )
    session.add(payment_session)
    session.commit()
    session.refresh(payment_session)

    return serialize_session(payment_session, request)


@app.post("/join", response_model=JoinResponse)
def join_session(
    data: JoinRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Вызывается мини-приложением сразу при открытии по диплинку.
    initData валидируется по HMAC — user_id берём только оттуда, никогда из тела запроса.
    """
    payload = validate_max_init_data(
        data.init_data,
        request,
        demo_user_id=DEMO_PARTICIPANT_ID,
    )

    user = payload.get("user")
    if not isinstance(user, dict) or "id" not in user:
        raise HTTPException(400, "В initData нет данных пользователя")
    user_id = user["id"]
    first_name = user.get("first_name")

    payment_session = session.exec(
        select(PaymentSession).where(PaymentSession.token == data.start_param)
    ).first()
    if not payment_session:
        raise HTTPException(404, "Сессия платежа не найдена — проверьте ссылку")

    participant = session.exec(
        select(Participant).where(
            Participant.session_id == payment_session.id,
            Participant.user_id == user_id,
        )
    ).first()

    if not participant:
        if payment_session.remaining_amount_cents <= 0:
            raise HTTPException(409, "Сбор уже закрыт")
        joined_count = session.exec(
            select(Participant.id).where(Participant.session_id == payment_session.id)
        ).all()
        if payment_session.payment_mode == "equal":
            if len(joined_count) >= payment_session.head_count:
                raise HTTPException(409, "Все места в сборе уже заняты")
            total_cents = amount_to_cents(payment_session.total_amount)
            base_share, remainder = divmod(total_cents, payment_session.head_count)
            share_cents = base_share + (1 if len(joined_count) < remainder else 0)
        else:
            share_cents = 0
        participant = Participant(
            session_id=payment_session.id,
            user_id=user_id,
            first_name=first_name,
            share_amount=share_cents / 100,
        )
        session.add(participant)
        session.commit()
        session.refresh(participant)

    return JoinResponse(
        participant_id=participant.id,
        session_title=payment_session.title,
        share_amount=participant.share_amount,
        total_amount=payment_session.total_amount,
        remaining_amount=payment_session.remaining_amount_cents / 100,
        payment_mode=payment_session.payment_mode,
        requisites=payment_session.requisites,
        status=participant.status,
    )


@app.post("/confirm")
def confirm_payment(
    data: ConfirmRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """Участник вручную подтверждает, что перевёл деньги по реквизитам."""
    payload = validate_max_init_data(
        data.init_data,
        request,
        demo_user_id=DEMO_PARTICIPANT_ID,
    )

    user = payload.get("user") or {}
    user_id = user.get("id")

    participant = session.get(Participant, data.participant_id)
    if not participant:
        raise HTTPException(404, "Участник не найден")
    if participant.user_id != user_id:
        # защита от подтверждения оплаты за другого человека чужим initData
        raise HTTPException(403, "Нельзя подтвердить оплату за другого участника")

    if participant.status == ParticipantStatus.paid:
        return {"status": "ok", "already_paid": True}

    payment_session = session.get(PaymentSession, participant.session_id)
    if not payment_session:
        raise HTTPException(404, "Сбор не найден")

    if payment_session.payment_mode == "equal":
        contribution_cents = amount_to_cents(participant.share_amount)
        if data.contribution_amount is not None and amount_to_cents(data.contribution_amount) != contribution_cents:
            raise HTTPException(400, "В режиме «Поровну» нужно внести рассчитанную долю")
    else:
        if data.contribution_amount is None:
            raise HTTPException(400, "Укажите сумму своего взноса")
        contribution_cents = amount_to_cents(data.contribution_amount)
        if contribution_cents <= 0:
            raise HTTPException(400, "Сумма взноса должна быть больше нуля")

    result = session.exec(
        text(
            "UPDATE paymentsession "
            "SET remaining_amount_cents = remaining_amount_cents - :amount "
            "WHERE id = :session_id AND remaining_amount_cents >= :amount"
        ),
        params={"amount": contribution_cents, "session_id": payment_session.id},
    )
    if result.rowcount != 1:
        raise HTTPException(409, "Взнос превышает оставшуюся сумму сбора")

    participant.status = ParticipantStatus.paid
    participant.confirmed_at = datetime.utcnow()
    participant.contribution_amount_cents = contribution_cents
    session.add(participant)
    session.commit()
    session.refresh(payment_session)

    if payment_session.organizer_id is not None:
        organizer = session.get(BotUser, payment_session.organizer_id)
        if organizer:
            name = participant.first_name or f"участник {participant.user_id}"
            background_tasks.add_task(
                send_message,
                organizer.chat_with_bot_id,
                f"{name} подтвердил(а) оплату {participant.share_amount}₽ по «{payment_session.title}»",
            )

    return {
        "status": "ok",
        "already_paid": False,
        "remaining_amount": payment_session.remaining_amount_cents / 100,
    }


@app.get("/sessions/{session_id}/status", response_model=SessionStatusOut)
def session_status(
    session_id: int,
    request: Request,
    x_max_init_data: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
):
    """Табличка для организатора: кто присоединился и кто уже оплатил."""
    organizer_id = require_user_id(x_max_init_data, request)
    payment_session = session.get(PaymentSession, session_id)
    if not payment_session or payment_session.organizer_id != organizer_id:
        raise HTTPException(404, "Сессия не найдена")

    participants = session.exec(
        select(Participant).where(Participant.session_id == session_id)
    ).all()

    return SessionStatusOut(
        id=payment_session.id,
        title=payment_session.title,
        total_amount=payment_session.total_amount,
        remaining_amount=payment_session.remaining_amount_cents / 100,
        payment_mode=payment_session.payment_mode,
        head_count=payment_session.head_count,
        joined_count=len(participants),
        paid_count=sum(1 for p in participants if p.status == ParticipantStatus.paid),
        participants=[
            ParticipantOut(
                user_id=p.user_id,
                first_name=p.first_name,
                share_amount=p.share_amount,
                contribution_amount=p.contribution_amount_cents / 100,
                status=p.status,
            )
            for p in participants
        ],
    )


@app.post("/webhook/max")
async def max_webhook(
    update: dict,
    x_max_bot_api_secret: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
):
    """
    Слушает события бота Max. Единственное, что нам здесь нужно —
    запомнить chat_id, когда пользователь стартует бота (bot_started),
    чтобы потом иметь право написать ему уведомление первым.
    """
    if not MAX_WEBHOOK_SECRET:
        raise HTTPException(503, "MAX_WEBHOOK_SECRET не настроен")
    if not x_max_bot_api_secret or not hmac.compare_digest(
        x_max_bot_api_secret,
        MAX_WEBHOOK_SECRET,
    ):
        raise HTTPException(401, "Неверный секрет webhook")

    if update.get("update_type") == "bot_started":
        user = update.get("user") or {}
        user_id = user.get("user_id") or update.get("user_id")
        chat_id = update.get("chat_id")
        if user_id and chat_id:
            existing = session.get(BotUser, user_id)
            if existing:
                existing.chat_with_bot_id = chat_id
            else:
                existing = BotUser(user_id=user_id, chat_with_bot_id=chat_id)
            session.add(existing)
            session.commit()
            await send_message(
                chat_id=chat_id,
                text=(
                    "Привет! Здесь можно создать общий сбор и следить за подтверждениями. "
                    f"Откройте мини-приложение MAX: https://max.ru/{BOT_NAME}?startapp=organizer"
                ),
            )
    return {"ok": True}
