"""Pydantic request models for SabiLab API."""

from typing import List, Optional
from pydantic import BaseModel


class SessionCreateRequest(BaseModel):
    user_id: Optional[str] = None
    first_name: str = "Student"
    consent: bool = False
    scenario_id: str = "adaeze"
    teammate_ids: Optional[List[str]] = None
    mode: str = "demo"


class MessagePostRequest(BaseModel):
    sender: str
    text: str


class TaskSubmitRequest(BaseModel):
    session_id: str
    text: str
    user_id: Optional[str] = None


class ClarificationAnswerRequest(BaseModel):
    message_id: str
    answer: str


class CardPublishRequest(BaseModel):
    visible_fields: Optional[List[str]] = None
