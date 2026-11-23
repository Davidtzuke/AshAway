"""Request bodies shared by the interface and the orchestrator.

Kept apart from both servers so the interface can check requests without
importing anything from the orchestrator (and so without the model code).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AssessBody(BaseModel):
    """A request to assess one destination; `alternatives` asks for lower-risk options too."""

    place: str = Field(max_length=100)
    start: str = Field(max_length=20)
    end: str = Field(max_length=20)
    alternatives: bool = True


class CompareBody(BaseModel):
    """A request to compare 2 to 11 destinations on the same dates."""

    places: list[str] = Field(min_length=2, max_length=11)
    start: str = Field(max_length=20)
    end: str = Field(max_length=20)


class FeedbackBody(BaseModel):
    """A traveller saying an assessment looks wrong (SRS AI8). Reviewed by the team, never learned from automatically."""

    verdict: Literal["risk_too_high", "risk_too_low", "evidence_wrong", "other"]
    comment: str | None = Field(default=None, max_length=500)
