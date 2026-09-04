from __future__ import annotations

from typing import Literal

from app.models import (
    AiSummary,
    ChangeEvent,
    Document,
    DocumentTranslation,
    DocumentVersion,
    Finding,
    IngestionRun,
    WarningLetter,
)
from app.schemas import (
    ChangeResponse,
    DocumentResponse,
    FindingResponse,
    IngestionRunResponse,
    LetterAiArtifactResponse,
    LetterListItem,
    SummaryResponse,
    VersionResponse,
)


def letter_item(
    letter: WarningLetter,
    *,
    documents: list[Document],
    summary: AiSummary | None,
    findings: list[Finding],
) -> LetterListItem:
    document_types = {document.document_type for document in documents}
    categories = sorted({category for item in findings for category in (item.categories or [])})
    return LetterListItem(
        id=letter.id,
        company_name=letter.company_name,
        country=letter.country,
        subject=letter.subject,
        canonical_url=letter.canonical_url,
        marcs_cms_number=letter.marcs_cms_number,
        posted_date=letter.posted_date,
        issue_date=letter.issue_date,
        issuing_offices=letter.issuing_offices or [],
        scope_status=letter.scope_status,
        normalized_product_classes=letter.normalized_product_classes or [],
        drug_subtypes=letter.drug_subtypes or [],
        lifecycle_status=letter.lifecycle_status,
        has_response="response" in document_types,
        has_closeout="closeout" in document_types,
        review_state=summary.review_state if summary else None,
        categories=categories,
        first_seen_at=letter.first_seen_at,
        last_seen_at=letter.last_seen_at,
        updated_at=letter.updated_at,
    )


def document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        document_type=document.document_type,
        title=document.title,
        canonical_url=document.canonical_url,
        issue_date=document.issue_date,
        source_available=document.source_available,
        current_version_id=document.current_version_id,
    )


def version_response(version: DocumentVersion, document: Document) -> VersionResponse:
    return VersionResponse(
        id=version.id,
        document_id=version.document_id,
        document_type=document.document_type,
        version_number=version.version_number,
        canonical_hash=version.canonical_hash,
        raw_sha256=version.raw_sha256,
        scope_status=version.scope_status,
        parser_version=version.parser_version,
        retrieved_at=version.retrieved_at,
        last_seen_at=version.last_seen_at,
        source_url=document.canonical_url,
        anchors=version.source_anchors or [],
    )


def summary_response(summary: AiSummary) -> SummaryResponse:
    return SummaryResponse(
        id=summary.id,
        document_version_id=summary.document_version_id,
        parent_summary_id=summary.parent_summary_id,
        revision=summary.revision,
        executive_summary=summary.executive_summary,
        language=summary.language,
        review_state=summary.review_state,
        validation_report=summary.validation_report or {},
        taxonomy_version=summary.taxonomy_version,
        created_at=summary.created_at,
    )


def finding_response(finding: Finding) -> FindingResponse:
    return FindingResponse(
        id=finding.id,
        label=finding.label,
        categories=finding.categories or [],
        process_lenses=finding.process_lenses or [],
        finding=finding.finding_text,
        regulatory_references=finding.regulatory_references or [],
        evidence=finding.evidence or [],
        fda_requested_actions=finding.fda_requested_actions or [],
        comparison_points=finding.comparison_points or [],
        attention_level=finding.attention_level,
        confidence=finding.confidence,
        review_state=finding.review_state,
    )


def translation_artifact_response(
    translation: DocumentTranslation,
) -> LetterAiArtifactResponse:
    return LetterAiArtifactResponse(
        id=translation.id,
        document_version_id=translation.document_version_id,
        artifact_type="translation",
        language="ko",
        content={"sections": translation.translated_sections or []},
        provider=translation.provider,
        model_id=translation.model_id,
        prompt_version=translation.prompt_version,
        source_hash=translation.source_hash,
        created_at=translation.created_at,
    )


def analysis_artifact_response(
    summary: AiSummary,
    findings: list[Finding],
    *,
    artifact_type: Literal["findings", "summary"],
) -> LetterAiArtifactResponse:
    structured = summary.structured_output or {}
    if artifact_type == "findings":
        content: dict[str, object] = {
            "findings": [
                {
                    "label": finding.label,
                    "title": next(
                        (
                            str(item.get("title"))
                            for item in (finding.evidence or [])
                            if item.get("title")
                        ),
                        finding.label,
                    ),
                    "finding": finding.finding_text,
                    "requested_actions": finding.fda_requested_actions or [],
                    "categories": finding.categories or [],
                    "attention_level": finding.attention_level or "routine",
                    "evidence_anchors": [
                        str(item["source_anchor"])
                        for item in (finding.evidence or [])
                        if item.get("source_anchor")
                    ],
                }
                for finding in findings
            ]
        }
    else:
        content = {
            "executive_summary": summary.executive_summary,
            "attention_points": structured.get("attention_points", []),
            "comparison_questions": structured.get("comparison_questions", []),
            "disclaimer": structured.get("disclaimer", ""),
        }
    return LetterAiArtifactResponse(
        id=summary.id,
        document_version_id=summary.document_version_id,
        artifact_type=artifact_type,
        language=summary.language,
        content=content,
        provider=summary.provider,
        model_id=summary.model_id,
        prompt_version=summary.prompt_version,
        source_hash=str(structured.get("source_hash", "")),
        created_at=summary.created_at,
    )


def change_response(event: ChangeEvent, company_name: str) -> ChangeResponse:
    return ChangeResponse(
        id=event.id,
        warning_letter_id=event.warning_letter_id,
        company_name=company_name,
        event_type=event.event_type,
        before_state=event.before_state,
        after_state=event.after_state,
        source_version_id=event.source_version_id,
        detected_at=event.detected_at,
        published_at=event.published_at,
    )


def ingestion_run_response(run: IngestionRun) -> IngestionRunResponse:
    return IngestionRunResponse(
        id=run.id,
        run_type=run.run_type,
        source=run.source,
        status=run.status,
        requested_by=run.requested_by,
        parser_version=run.parser_version,
        scope_rule_version=run.scope_rule_version,
        started_at=run.started_at,
        completed_at=run.completed_at,
        metrics=run.metrics or {},
        error_code=run.error_code,
        created_at=run.created_at,
    )
