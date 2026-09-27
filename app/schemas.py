from typing import List, Optional
from decimal import Decimal

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str
    total_amount: float
    head_count: int
    payment_mode: str = Field(default="equal", pattern="^(equal|flexible)$")
    requisites: str
    init_data: str


class SessionOut(BaseModel):
    id: int
    title: str
    total_amount: float
    head_count: int
    payment_mode: str
    remaining_amount: float
    per_head: float
    link: str


class JoinRequest(BaseModel):
    init_data: str    # сырая строка WebAppData, для HMAC-проверки
    start_param: str  # session token, пришедший из ?startapp=


class JoinResponse(BaseModel):
    participant_id: int
    session_title: str
    share_amount: float
    total_amount: float
    remaining_amount: float
    payment_mode: str
    requisites: str
    status: str


class ConfirmRequest(BaseModel):
    init_data: str
    participant_id: int
    contribution_amount: Optional[Decimal] = Field(
        default=None,
        gt=Decimal("0"),
        max_digits=12,
        decimal_places=2,
    )


class ParticipantOut(BaseModel):
    user_id: int
    first_name: Optional[str]
    share_amount: float
    contribution_amount: float
    status: str


class SessionStatusOut(BaseModel):
    id: int
    title: str
    total_amount: float
    remaining_amount: float
    payment_mode: str
    head_count: int
    joined_count: int
    paid_count: int
    participants: List[ParticipantOut]
