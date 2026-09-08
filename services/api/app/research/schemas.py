from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MODEL_CALLS = 12
MAX_TOTAL_TOKENS = 90_000
MAX_EVIDENCE = 12


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateResearch(Strict):
    objective: str = Field(min_length=8, max_length=2_000)
    language: Literal["en", "ko"] = "ko"
    client_request_id: UUID

    @field_validator("objective")
    @classmethod
    def clean_objective(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 8:
            raise ValueError("Describe the research task in at least eight characters")
        return value


class PlanResearch(Strict):
    steps: list[str] = Field(min_length=2, max_length=5)

    @field_validator("steps")
    @classmethod
    def bounded_steps(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 180 for value in values):
            raise ValueError("Plan steps must be short task descriptions")
        return values


class SearchSources(Strict):
    query: str = Field(min_length=2, max_length=180)


class ReadSources(Strict):
    chunk_ids: list[UUID] = Field(min_length=1, max_length=6)


class CitedFinding(Strict):
    statement: str = Field(min_length=10, max_length=1_200)
    citation_ids: list[str] = Field(min_length=1, max_length=4)


class SubmitBrief(Strict):
    title: str = Field(min_length=5, max_length=180)
    findings: list[CitedFinding] = Field(min_length=1, max_length=8)
    review_questions: list[str] = Field(min_length=1, max_length=6)
    limitations: list[str] = Field(min_length=1, max_length=5)

    @field_validator("review_questions", "limitations")
    @classmethod
    def bounded_text(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 600 for value in values):
            raise ValueError("Review questions and limitations must be concise")
        return values


class NoEvidence(Strict):
    explanation: str = Field(min_length=10, max_length=600)


class EvidenceCheck(Strict):
    supported: bool
    issues: list[str] = Field(max_length=8)


TOOL_MODELS = {
    "plan_research": PlanResearch,
    "search_sources": SearchSources,
    "read_sources": ReadSources,
    "submit_brief": SubmitBrief,
    "report_no_evidence": NoEvidence,
}
