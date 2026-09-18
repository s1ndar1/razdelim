from typing import List, Optional

from pydantic import BaseModel


class SessionCreate(BaseModel):
    title: str
    total_amount: float
    head_count: int
    requisites: str


class SessionOut(BaseModel):
    id: int
    title: str
    total_amount: float
    head_count: int
    per_head: float
    link: str


class JoinRequest(BaseModel):
    init_data: str    # сырая строка WebAppData, для HMAC-проверки
    start_param: str  # session token, пришедший из ?startapp=


class JoinResponse(BaseModel):
    participant_id: int
    session_title: str
    share_amount: float
    requisites: str
    status: str


class ConfirmRequest(BaseModel):
    init_data: str
    participant_id: int


class ParticipantOut(BaseModel):
    user_id: int
    first_name: Optional[str]
    share_amount: float
    status: str


class SessionStatusOut(BaseModel):
    id: int
    title: str
    total_amount: float
    head_count: int
    joined_count: int
    paid_count: int
    participants: List[ParticipantOut]
