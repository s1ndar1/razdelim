import secrets
import string
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlmodel import Session, select

from .bot import send_message
from .config import BOT_NAME, BOT_TOKEN
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


@app.post("/sessions", response_model=SessionOut)
def create_session(data: SessionCreate, session: Session = Depends(get_session)):
    """Организатор создаёт запрос на скидывание. Возвращает диплинк для группы."""
    if data.head_count < 1:
        raise HTTPException(400, "head_count должен быть не меньше 1")
    if data.total_amount <= 0:
        raise HTTPException(400, "total_amount должен быть больше 0")

    token = "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(12))

    payment_session = PaymentSession(
        title=data.title,
        total_amount=data.total_amount,
        head_count=data.head_count,
        requisites=data.requisites,
        token=token,
    )
    session.add(payment_session)
    session.commit()
    session.refresh(payment_session)

    link = f"https://max.ru/{BOT_NAME}?startapp={token}"
    return SessionOut(
        id=payment_session.id,
        title=payment_session.title,
        total_amount=payment_session.total_amount,
        head_count=payment_session.head_count,
        per_head=round(payment_session.total_amount / payment_session.head_count, 2),
        link=link,
    )


@app.post("/join", response_model=JoinResponse)
def join_session(data: JoinRequest, session: Session = Depends(get_session)):
    """
    Вызывается мини-приложением сразу при открытии по диплинку.
    initData валидируется по HMAC — user_id берём только оттуда, никогда из тела запроса.
    """
    payload = validate_init_data(data.init_data, BOT_TOKEN)
    if payload is None:
        raise HTTPException(401, "Не удалось подтвердить подлинность initData")

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
        participant = Participant(
            session_id=payment_session.id,
            user_id=user_id,
            first_name=first_name,
            share_amount=round(payment_session.total_amount / payment_session.head_count, 2),
        )
        session.add(participant)
        session.commit()
        session.refresh(participant)

    return JoinResponse(
        participant_id=participant.id,
        session_title=payment_session.title,
        share_amount=participant.share_amount,
        requisites=payment_session.requisites,
        status=participant.status,
    )


@app.post("/confirm")
def confirm_payment(
    data: ConfirmRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """Участник вручную подтверждает, что перевёл деньги по реквизитам."""
    payload = validate_init_data(data.init_data, BOT_TOKEN)
    if payload is None:
        raise HTTPException(401, "Не удалось подтвердить подлинность initData")

    user = payload.get("user") or {}
    user_id = user.get("id")

    participant = session.get(Participant, data.participant_id)
    if not participant:
        raise HTTPException(404, "Участник не найден")
    if participant.user_id != user_id:
        # защита от подтверждения оплаты за другого человека чужим initData
        raise HTTPException(403, "Нельзя подтвердить оплату за другого участника")

    participant.status = ParticipantStatus.paid
    participant.confirmed_at = datetime.utcnow()
    session.add(participant)
    session.commit()

    payment_session = session.get(PaymentSession, participant.session_id)
    if payment_session.organizer_id is not None:
        organizer = session.get(BotUser, payment_session.organizer_id)
        if organizer:
            name = participant.first_name or f"участник {participant.user_id}"
            background_tasks.add_task(
                send_message,
                organizer.chat_with_bot_id,
                f"{name} подтвердил(а) оплату {participant.share_amount}₽ по «{payment_session.title}»",
            )

    return {"status": "ok"}


@app.get("/sessions/{session_id}/status", response_model=SessionStatusOut)
def session_status(session_id: int, session: Session = Depends(get_session)):
    """Табличка для организатора: кто присоединился и кто уже оплатил."""
    payment_session = session.get(PaymentSession, session_id)
    if not payment_session:
        raise HTTPException(404, "Сессия не найдена")

    participants = session.exec(
        select(Participant).where(Participant.session_id == session_id)
    ).all()

    return SessionStatusOut(
        id=payment_session.id,
        title=payment_session.title,
        total_amount=payment_session.total_amount,
        head_count=payment_session.head_count,
        joined_count=len(participants),
        paid_count=sum(1 for p in participants if p.status == ParticipantStatus.paid),
        participants=[
            ParticipantOut(
                user_id=p.user_id,
                first_name=p.first_name,
                share_amount=p.share_amount,
                status=p.status,
            )
            for p in participants
        ],
    )


@app.post("/webhook/max")
async def max_webhook(update: dict, session: Session = Depends(get_session)):
    """
    Слушает события бота Max. Единственное, что нам здесь нужно —
    запомнить chat_id, когда пользователь стартует бота (bot_started),
    чтобы потом иметь право написать ему уведомление первым.
    """
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
    return {"ok": True}
