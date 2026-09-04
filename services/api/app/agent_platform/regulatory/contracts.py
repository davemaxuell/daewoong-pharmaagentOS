"""Strict runtime types for RegulatoryFindingList@2.0.0.

These types intentionally contain only inspectable result data. Provider thoughts, hidden
reasoning, prompt text, and arbitrary metadata are not represented by the contract.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Sha256 = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$"),
]
AnchorId = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=256,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
FindingId = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=4,
        max_length=80,
        pattern=r"^rf-[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
BoundedText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=5000),
]


class QualitySystemCategory(StrEnum):
    QUALITY_UNIT = "Quality Unit / QA Oversight"
    DOCUMENTATION = "Documentation / GDP / Batch Records"
    DATA_INTEGRITY = "Data Integrity / Computerized Systems / Audit Trail"
    TRAINING = "Training / Qualification / Personnel Practices"
    INVESTIGATIONS = "Deviations / Investigations / OOS / OOT / CAPA"
    ASEPTIC_PROCESSING = "Aseptic Processing / Sterility Assurance / Media Fill"
    CONTAMINATION_CONTROL = "Contamination Control / Cleaning / Disinfection"
    PROCESS_VALIDATION = "Process Validation / PPQ / Continued Process Verification"
    EQUIPMENT = "Equipment / Qualification / Calibration / Maintenance"
    FACILITIES = "Facilities / Utilities / HVAC / Water Systems"
    LABORATORY_CONTROLS = "Laboratory Controls / Method Validation / Microbiology"
    STABILITY = "Stability / Expiry / Retest / Reserve Samples"
    MATERIALS = "Materials / Components / Supplier Qualification / COA Reliability"
    PACKAGING = "Packaging / Labeling / Container-Closure"
    COMPLAINTS = "Complaints / Adverse Events / Recall / Market Action"
    OUTSOURCED_ACTIVITIES = "Contract Manufacturing / Contract Laboratory / Outsourced Activities"
    API_MANUFACTURING = "API Manufacturing / ICH Q7-related CGMP"
    REGISTRATION = "Drug Establishment Registration / Listing / NDC"
    MARKETING_AUTHORIZATION = "Misbranding / Unapproved Drug / Marketing Authorization"
    DISTRIBUTION = "Distribution / Warehousing / Supply Chain"
    CHANGE_MANAGEMENT = "Change Management"
    OTHER = "Other Drug Regulatory / CGMP"


class ProcessLens(StrEnum):
    PREVENTIVE = "preventive"
    MONITORING = "monitoring"
    RETROSPECTIVE = "retrospective"


class ExtractionWarningCode(StrEnum):
    AMBIGUOUS_SCOPE = "AMBIGUOUS_SCOPE"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    OCR_QUALITY = "OCR_QUALITY"
    PARTIAL_SOURCE = "PARTIAL_SOURCE"
    OTHER = "OTHER"


class EvidenceAnchor(_StrictContract):
    source_version_id: UUID
    source_hash: Sha256
    anchor_id: AnchorId
    excerpt: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4000)]
    excerpt_sha256: Sha256
    evidence_class: Literal["PRIMARY_AUTHORITATIVE"]


class RegulatoryReference(_StrictContract):
    reference: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=500)]
    evidence_anchor_ids: list[AnchorId] = Field(min_length=1, max_length=20)

    @field_validator("evidence_anchor_ids")
    @classmethod
    def anchor_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_anchor_ids must be unique")
        return value


class RequestedAction(_StrictContract):
    action: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=3000)]
    evidence_anchor_ids: list[AnchorId] = Field(min_length=1, max_length=20)

    @field_validator("evidence_anchor_ids")
    @classmethod
    def anchor_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_anchor_ids must be unique")
        return value


class ExtractionWarning(_StrictContract):
    code: ExtractionWarningCode
    message: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
    evidence_anchor_ids: list[AnchorId] = Field(max_length=20)

    @field_validator("evidence_anchor_ids")
    @classmethod
    def anchor_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_anchor_ids must be unique")
        return value


class RegulatoryFinding(_StrictContract):
    finding_id: FindingId
    source_version_id: UUID
    source_hash: Sha256
    title: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=500)]
    finding_text: BoundedText
    quality_system_categories: list[QualitySystemCategory] = Field(
        min_length=1,
        max_length=len(QualitySystemCategory),
    )
    process_lenses: list[ProcessLens] = Field(min_length=1, max_length=len(ProcessLens))
    regulatory_references: list[RegulatoryReference] = Field(max_length=50)
    fda_requested_actions: list[RequestedAction] = Field(max_length=30)
    evidence: list[EvidenceAnchor] = Field(min_length=1, max_length=20)
    confidence: Annotated[float, Field(strict=True, ge=0, le=1)]
    extraction_warnings: list[ExtractionWarning] = Field(max_length=20)

    @field_validator("quality_system_categories", "process_lenses")
    @classmethod
    def enum_values_are_unique(cls, value: list[StrEnum]) -> list[StrEnum]:
        if len(value) != len(set(value)):
            raise ValueError("controlled vocabulary values must be unique")
        return value


class RegulatoryFindingList(_StrictContract):
    schema_version: Literal["2.0.0"]
    taxonomy_version: Annotated[
        str,
        StringConstraints(
            strict=True,
            max_length=80,
            pattern=r"^drug-taxonomy-v[0-9]+\.[0-9]+\.[0-9]+$",
        ),
    ]
    findings: list[RegulatoryFinding] = Field(min_length=1, max_length=50)

    @field_validator("findings")
    @classmethod
    def finding_ids_are_unique(cls, value: list[RegulatoryFinding]) -> list[RegulatoryFinding]:
        finding_ids = [finding.finding_id for finding in value]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding_id values must be unique")
        return value


QUALITY_SYSTEM_CATEGORY_VALUES = frozenset(item.value for item in QualitySystemCategory)
PROCESS_LENS_VALUES = frozenset(item.value for item in ProcessLens)
