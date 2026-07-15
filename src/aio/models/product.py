"""Structured output for the Product Manager once it's research-driven."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserStory(BaseModel):
    as_a: str
    i_want: str
    so_that: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class Epic(BaseModel):
    title: str
    description: str
    user_stories: list[UserStory] = Field(default_factory=list)


class ProductVision(BaseModel):
    statement: str
    target_users: list[str] = Field(default_factory=list)
    value_proposition: str


class Risk(BaseModel):
    description: str
    likelihood: str  # "low" | "medium" | "high"
    impact: str  # "low" | "medium" | "high"
    mitigation: str


class SuccessMetric(BaseModel):
    name: str
    target: str
    rationale: str


class ReleasePhase(BaseModel):
    name: str
    scope: str
    epics: list[str] = Field(default_factory=list)


class BusinessRequirementsDocument(BaseModel):
    vision: ProductVision
    epics: list[Epic] = Field(default_factory=list)
    release_roadmap: list[ReleasePhase] = Field(default_factory=list)
    sprint_suggestions: list[str] = Field(default_factory=list)
    risk_register: list[Risk] = Field(default_factory=list)
    success_metrics: list[SuccessMetric] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str
