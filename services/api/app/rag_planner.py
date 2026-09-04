from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

RetrievalMode = Literal["auto", "none", "metadata", "letter", "corpus"]
RetrievalStrategy = Literal["none", "metadata", "letter", "multi_letter", "corpus"]
ModelProfile = Literal["auto", "fast", "balanced", "deep"]
EffectiveModelProfile = Literal["fast", "balanced", "deep"]


@dataclass(frozen=True)
class RagPlan:
    retrieval_strategy: RetrievalStrategy
    route_reason: str
    letter_ids: tuple[str, ...] = ()
    internal_comparison: bool = False
    deterministic_response: Literal["capabilities", "out_of_scope", "scope_required"] | None = None


_GREETING_RE = re.compile(
    r"^(?:hi|hello|hey|thanks|thank you|안녕(?:하세요)?|감사(?:합니다|해요)?)[!,.?\s]*$",
    re.IGNORECASE,
)
_HELP_RE = re.compile(
    r"(?:what can you do|how (?:do i|to) use|help me use|사용법|무엇을 할 수|어떻게 사용|"
    r"모델 (?:변경|선택)|change (?:the )?model|settings?)",
    re.IGNORECASE,
)
_OUT_OF_SCOPE_RE = re.compile(
    r"(?:\b(?:weather|sports scores?|stock prices?|share prices?|market cap(?:italization)?|"
    r"recipes?|cooking|bak(?:e|ing)|sourdough|bread making|movie recommendations?|song lyrics?|"
    r"video games?|restaurants?|"
    r"travel itinerar(?:y|ies)|hotels?|flights?|politics|elections?)\b|"
    r"\b(?:chief executive officer|ceo|founders?|headquarters|investor relations|careers?|"
    r"job openings?|quarterly earnings|annual revenue)\b|"
    r"\b(?:medical diagnosis|dose recommendation|treatment recommendation|legal advice)\b|"
    r"날씨|스포츠 (?:점수|결과)|주가|시가총액|요리법|영화 추천|노래 가사|게임 추천|"
    r"맛집|여행 일정|호텔 추천|항공권|정치|선거|대표이사|최고경영자|창업자|본사|"
    r"투자자 관계|채용|구인|분기 실적|연간 매출|의학적 진단|복용량 추천|치료 추천|"
    r"법률 자문)",
    re.IGNORECASE,
)
_DOMAIN_RE = re.compile(
    r"(?:\bwarning[-\s]?letters?\b|"
    r"\b(?:c?gmp|21\s*cfr|cfr|oos|oot|capa|marcs(?:-cms)?)(?=\b|[가-힣])|"
    r"\b(?:pharma(?:ceutical)?|good manufacturing practices?|drug development|drug products?|"
    r"active pharmaceutical ingredients?|batch release|"
    r"root cause analysis|corrective actions?|preventive actions?|quality remediation|"
    r"inspection readiness|manufacturing (?:site|facility)|product quality|impurit(?:y|ies)|"
    r"dissolution testing|potency testing|microbial controls?|process validation|"
    r"continued process verification|"
    r"quality unit|data integrity|"
    r"audit trails?|batch records?|laboratory controls?|stability (?:program|testing|data|study)|"
    r"retest periods?|aseptic|sterilization|depyrogenation|cleanrooms?|media fills?|"
    r"environmental monitoring|supplier qualification|certificates? of analysis|"
    r"drug manufacturing|pharmaceutical quality|regulatory (?:citation|inspection|finding|"
    r"evidence|quality|reference)|issuing office|posted date|issue date|recipient country|"
    r"source-backed|FDA source|drug manufacturers?|corpus)\b|"
    r"\bfda\b.{0,80}\b(?:warning|letter|source|inspection|finding|observation|request|drug|"
    r"quality|manufactur|regulatory)\w*\b|"
    r"\b(?:warning|letter|source|inspection|finding|observation|request|drug|quality|"
    r"manufactur|regulatory)\w*\b.{0,80}\bfda\b|"
    r"경고(?:장|서(?:한)?)|FDA\s*원문|제약|의약품?|원료\s*의약품|완제\s*의약품|"
    r"제조소|제조\s*시설|근본\s*원인|원인\s*조사|시정\s*조치|예방\s*조치|"
    r"개선\s*조치|공정\s*밸리데이션|지속적\s*공정\s*검증|데이터\s*무결성|"
    r"품질\s*부서|품질\s*관리|감사\s*추적|기준일탈|일탈\s*조사|CAPA|배치\s*기록|"
    r"시험실\s*관리|안정성\s*(?:시험|자료|프로그램)|재시험|무균|멸균|오염|청정구역|"
    r"환경\s*모니터링|공급업체\s*적격|시험성적서|의약품\s*(?:제조|품질)|규정\s*인용|"
    r"규제\s*(?:근거|점검|품질)|발행일|게시일|발행\s*부서|수신인\s*국가|지적\s*사항|"
    r"위반\s*사항|요청(?:한|\s*)\s*조치|FDA가.{0,80}(?:요청|지적|설명)|코퍼스)",
    re.IGNORECASE,
)
_METADATA_RE = re.compile(
    r"(?:official (?:url|link)|source (?:url|link)|when (?:was|did).*(?:issued|posted)|"
    r"issue date|posted date|recipient country|issuing office|how many (?:letters|warning)|"
    r"latest (?:letter|warning)|원문 (?:주소|링크)|발행일|게시일|수신인 국가|발행 부서|"
    r"경고장 (?:수|개수)|최신 경고장)",
    re.IGNORECASE,
)
_BROAD_RE = re.compile(
    r"(?:trend|pattern|across|common|overall|recurr|most often|over time|vary by|\bcompare\b|"
    r"all (?:letters|manufacturers)|which letters|추세|경향|공통|반복|가장 자주|시간에 따라|"
    r"어떻게 다른|비교|전체|여러 (?:경고장|회사)|경고장 간 비교)",
    re.IGNORECASE,
)
_COMPARISON_RE = re.compile(
    r"(?:our (?:pipeline|process|workflow|system)|daewoong|same (?:issue|problem)|"
    r"similar (?:issue|risk)|internal (?:comparison|check)|우리(?:의)? (?:파이프라인|공정|"
    r"워크플로|시스템|pipeline|process|workflow|system)|대웅|동일한 (?:문제|이슈)|"
    r"유사한 (?:문제|위험)|내부 (?:비교|점검))",
    re.IGNORECASE,
)
_FOLLOW_UP_RE = re.compile(
    r"(?:\b(?:it|its|they|them|their|there|that|this letter|the letter|the company|"
    r"that company)\b|what else|what about|what did (?:they|fda)|"
    r"(?:tell me more|summari[sz]e|translate|key points?|what happened)"
    r"(?:\s+(?:it|this|that|the letter))?[?.!\s]*$|explain (?:it|this)|"
    r"(?:그|이|해당) 경고(?:장|서(?:한)?)|그 문서|이 문서|더 알려|또 무엇|"
    r"FDA가 무엇|그 회사|그 업체|그들의|그곳|나머지|그건|"
    r"(?:요약|번역|설명|핵심)(?:해|해줘|해주세요|만)?[?.!\s]*$)",
    re.IGNORECASE,
)
_EVIDENCE_RE = re.compile(
    r"(?:\b(?:search|find|show|retrieve|cite|citation|evidence|source passage|according to|"
    r"manufacturer|finding|violation|observation|validation|cgmp|cfr|stability|retest|"
    r"data integrity|quality unit|contamination|aseptic|sterile|investigation|complaint|"
    r"reference standard|reagent|sample handling|computerized laboratory|expiry|pull schedule|"
    r"supplier|incoming component|yield|material reconciliation|equipment cleaning|"
    r"change control|in-process control|documentation|training record|sop)\b|"
    r"(?:cgmp|cfr)(?=\b|[가-힣])|what did (?:it|they|fda)|"
    r"which (?:letters|companies|manufacturers)|"
    r"찾아|검색|근거|인용|원문|제조업체|지적 사항|지적사항|위반 사항|위반사항|"
    r"공정 밸리데이션|데이터 무결성|품질 부서|안정성|재시험|무균|오염|"
    r"FDA가 .*?(?:말|요청|지적))",
    re.IGNORECASE,
)


def _unique_ids(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for group in groups for item in group if item))


def is_clearly_out_of_scope(question: str) -> bool:
    """Identify explicit non-domain requests without treating ambiguity as a refusal."""

    return bool(_OUT_OF_SCOPE_RE.search(" ".join(question.split())))


def _letter_plan(
    letter_ids: tuple[str, ...],
    reason: str,
    *,
    comparison: bool,
) -> RagPlan:
    strategy: RetrievalStrategy = "multi_letter" if len(letter_ids) > 1 else "letter"
    return RagPlan(strategy, reason, letter_ids, comparison)


def plan_rag(
    *,
    question: str,
    requested_mode: RetrievalMode = "auto",
    explicit_letter_ids: tuple[str, ...] = (),
    resolved_letter_ids: tuple[str, ...] = (),
    thread_active_letter_ids: tuple[str, ...] = (),
    prior_citation_letter_ids: tuple[str, ...] = (),
    prior_user_questions: tuple[str, ...] = (),
    semantic_domain_relevant: bool = False,
) -> RagPlan:
    """Choose a retrieval tool without inspecting document chunks or calling an LLM.

    Stable reason codes are intentionally coarse observability labels, not hidden reasoning.
    """

    question = " ".join(question.split())
    comparison = bool(_COMPARISON_RE.search(question))
    direct_ids = _unique_ids(explicit_letter_ids, resolved_letter_ids)
    inherited_ids = _unique_ids(thread_active_letter_ids, prior_citation_letter_ids)

    if _GREETING_RE.search(question) or _HELP_RE.search(question):
        return RagPlan("none", "capability_or_greeting", deterministic_response="capabilities")

    # A concrete current-request dossier or a company/MARCS name resolved from the authorized
    # corpus is strong application context. Inherited scope remains more conservative: it needs
    # either referential phrasing, prior domain context, or a semantic classification. Explicitly
    # unrelated requests are refused regardless of any selected dossier.
    has_referential_scope = bool((direct_ids or inherited_ids) and _FOLLOW_UP_RE.search(question))
    has_domain_follow_up = bool(
        _FOLLOW_UP_RE.search(question)
        and any(_DOMAIN_RE.search(prior_question) for prior_question in prior_user_questions)
    )
    has_scoped_evidence_intent = bool(
        (direct_ids or inherited_ids) and _EVIDENCE_RE.search(question)
    )
    domain_relevant = bool(
        comparison
        or direct_ids
        or has_referential_scope
        or has_domain_follow_up
        or has_scoped_evidence_intent
        or _DOMAIN_RE.search(question)
        or semantic_domain_relevant
    )
    if is_clearly_out_of_scope(question) or not domain_relevant:
        return RagPlan("none", "out_of_scope_request", deterministic_response="out_of_scope")

    if requested_mode == "none":
        if comparison:
            return RagPlan(
                "none",
                "internal_comparison_requires_letter_scope",
                internal_comparison=True,
                deterministic_response="scope_required",
            )
        return RagPlan("none", "user_requested_no_retrieval")
    if requested_mode == "metadata":
        return RagPlan("metadata", "user_requested_metadata", direct_ids or inherited_ids)
    if requested_mode == "corpus":
        # A concrete filter is an authorization-like retrieval boundary. Treat the
        # contradictory combination of an explicit letter filter and corpus mode as
        # letter-scoped rather than silently widening it. Resolved company/MARCS IDs may
        # still accompany an explicitly selected corpus request because that selection is
        # unambiguous at the current-request level; inherited thread defaults are handled by
        # the route before they reach the planner.
        if explicit_letter_ids:
            return _letter_plan(
                tuple(dict.fromkeys(explicit_letter_ids)),
                "explicit_letter_scope_overrides_corpus",
                comparison=comparison,
            )
        return RagPlan("corpus", "user_requested_corpus", internal_comparison=comparison)
    if requested_mode == "letter":
        ids = direct_ids or inherited_ids
        return _letter_plan(ids, "user_requested_letter_scope", comparison=comparison)

    if direct_ids:
        return _letter_plan(direct_ids, "explicit_or_resolved_letter_scope", comparison=comparison)
    if _METADATA_RE.search(question):
        return RagPlan("metadata", "structured_metadata_intent", inherited_ids)
    if _BROAD_RE.search(question):
        return RagPlan("corpus", "broad_corpus_analysis", internal_comparison=comparison)
    if comparison and inherited_ids:
        return _letter_plan(inherited_ids, "internal_comparison_inherited_scope", comparison=True)
    if comparison:
        return RagPlan(
            "none",
            "internal_comparison_requires_letter_scope",
            internal_comparison=True,
            deterministic_response="scope_required",
        )
    if inherited_ids and _FOLLOW_UP_RE.search(question):
        return _letter_plan(inherited_ids, "follow_up_inherited_scope", comparison=False)
    if thread_active_letter_ids:
        return _letter_plan(
            tuple(dict.fromkeys(thread_active_letter_ids)),
            "thread_active_letter_scope",
            comparison=comparison,
        )
    if _EVIDENCE_RE.search(question):
        return RagPlan("corpus", "evidence_search_intent", internal_comparison=comparison)
    return RagPlan("none", "general_conversation_no_retrieval")


def choose_model_profile(
    requested: ModelProfile,
    plan: RagPlan,
) -> EffectiveModelProfile:
    if requested != "auto":
        return requested
    if plan.internal_comparison:
        return "deep"
    if plan.retrieval_strategy in {"corpus", "multi_letter"}:
        return "balanced"
    return "fast"
