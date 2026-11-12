"""Pydantic request models for SabiLab API."""

from typing import List, Optional
from pydantic import BaseModel, field_validator
from app.card import normalize_visible_fields
from app.rubric import is_valid_criterion, is_valid_level


class SessionCreateRequest(BaseModel):
    user_id: Optional[str] = None
    first_name: str = "SabiLab learner"
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

    @field_validator("visible_fields")
    @classmethod
    def validate_visible_fields(cls, fields: Optional[List[str]]) -> Optional[List[str]]:
        return normalize_visible_fields(fields)


class ScoringRubricFields(BaseModel):
    """Rubric-constrained fields shared by the LLM scoring verifier."""

    criterion: str
    level: str

    @field_validator("criterion")
    @classmethod
    def validate_criterion(cls, criterion: str) -> str:
        if not is_valid_criterion(criterion):
            raise ValueError("Criterion is not recognized in rubric.json.")
        return criterion

    @field_validator("level")
    @classmethod
    def validate_level(cls, level: str) -> str:
        if not is_valid_level(level):
            raise ValueError("Level is not defined in rubric.json.")
        return level


class DraftSaveRequest(BaseModel):
    text: str
