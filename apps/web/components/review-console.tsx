"use client";

import Link from "next/link";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  ExternalLink,
  FileCheck2,
  Fingerprint,
  Layers3,
  Quote,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState, useTransition } from "react";
import {
  refreshReviewQueue,
  submitReviewDecision,
} from "@/app/(portal)/review/actions";
import { PageGuide } from "@/components/page-guide";
import { formatDate, ModeBadge, StatusPill } from "@/components/ui";
import type {
  ReviewQueueData,
  ReviewQueueFilter,
  ReviewReceipt,
} from "@/lib/api-client";
import { useI18n } from "@/lib/i18n";
import type { DataMode, ReviewItem, ReviewState } from "@/lib/types";

type DeferredAction =
  | { kind: "select"; itemId: string }
  | { kind: "queue"; view: ReviewQueueFilter; cursor?: string; pageSize: number };

export function ReviewConsole({
  initialQueue,
  mode,
}: {
  initialQueue: ReviewQueueData;
  mode: DataMode;
}) {
  const { locale, text } = useI18n();
  const [queue, setQueue] = useState(initialQueue);
  const [view, setView] = useState<ReviewQueueFilter>("open");
  const [cursor, setCursor] = useState<string>();
  const [selectedId, setSelectedId] = useState(initialQueue.items[0]?.id ?? "");
  const [reason, setReason] = useState("");
  const [editedFinding, setEditedFinding] = useState(initialQueue.items[0]?.aiFinding ?? "");
  const [error, setError] = useState<
    | "reason_required"
    | "unsupported_decision"
    | "edited_requires_approval"
    | "finding_too_short"
    | "version_conflict"
    | "decision_failed"
  >();
  const [queueError, setQueueError] = useState(false);
  const [receipt, setReceipt] = useState<ReviewReceipt>();
  const [deferredAction, setDeferredAction] = useState<DeferredAction>();
  const [pending, startTransition] = useTransition();
  const selected = queue.items.find((item) => item.id === selectedId);
  const reviewable = selected
    ? ["pending", "needs_revision"].includes(selected.state)
    : false;
  const isDirty = Boolean(
    selected &&
      reviewable &&
      (editedFinding !== selected.aiFinding || reason.trim().length > 0),
  );
  const derivedLanguage = /[가-힣]/.test(editedFinding) ? "ko" : "en";
  const totalPages = Math.max(1, Math.ceil(queue.total / queue.pageSize));

  useEffect(() => {
    if (!isDirty) return;
    const protectDraft = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", protectDraft);
    return () => window.removeEventListener("beforeunload", protectDraft);
  }, [isDirty]);

  const reviewRecordText = (value: string) => {
    const translations: Record<string, string> = {
      "High-impact aseptic category requires first-period human review": "영향도가 높은 무균 범주는 초기 기간에 사람의 검토가 필요합니다",
      "Source version changed while structured extraction was in flight": "구조화 추출 진행 중 원문 버전이 변경되었습니다",
      "Requested action excerpt does not exactly match normalized anchor": "요청 조치 발췌문이 정규화된 앵커와 정확히 일치하지 않습니다",
      "Confidence below 0.90": "신뢰도가 0.90 미만입니다",
      "Source-version consistency": "원문 버전 일관성",
      "Human approval is required by the active review policy": "현재 검토 정책에 따라 사람의 승인이 필요합니다",
    };
    return text(value, translations[value] ?? value);
  };

  const resetEditor = (item?: ReviewItem) => {
    setSelectedId(item?.id ?? "");
    setEditedFinding(item?.aiFinding ?? "");
    setReason("");
    setError(undefined);
  };

  const loadQueue = (
    nextView: ReviewQueueFilter,
    nextCursor: string | undefined,
    pageSize: number,
  ) => {
    setQueueError(false);
    startTransition(async () => {
      try {
        const result = await refreshReviewQueue({
          view: nextView,
          cursor: nextCursor,
          pageSize,
        });
        setQueue(result.data);
        setView(nextView);
        setCursor(nextCursor);
        const stillPresent = result.data.items.find((item) => item.id === selectedId);
        resetEditor(stillPresent ?? result.data.items[0]);
      } catch {
        setQueueError(true);
      }
    });
  };

  const executeAction = (action: DeferredAction) => {
    setDeferredAction(undefined);
    if (action.kind === "select") {
      resetEditor(queue.items.find((item) => item.id === action.itemId));
      return;
    }
    loadQueue(action.view, action.cursor, action.pageSize);
  };

  const requestAction = (action: DeferredAction) => {
    if (isDirty) {
      setDeferredAction(action);
      return;
    }
    executeAction(action);
  };

  const visibleItems = useMemo(() => queue.items, [queue.items]);

  const decide = (state: ReviewState) => {
    if (!selected || !reviewable) return;
    const findingChanged = editedFinding.trim() !== selected.aiFinding.trim();
    if (findingChanged && state !== "approved") {
      setError("edited_requires_approval");
      return;
    }
    setError(undefined);
    setReceipt(undefined);
    startTransition(async () => {
      try {
        const result = await submitReviewDecision(
          selected.summaryId,
          state,
          reason,
          findingChanged ? editedFinding : undefined,
          String(selected.summaryRevision),
        );
        const updated: ReviewItem = {
          ...selected,
          summaryId: result.resultingSummaryId,
          summaryRevision: result.resultingRevision,
          aiFinding: findingChanged ? editedFinding.trim() : selected.aiFinding,
          state: result.state,
        };
        const retainInQueue = view === "all" || result.state === "needs_revision";
        const updatedItems = retainInQueue
          ? queue.items.map((item) => (item.id === selected.id ? updated : item))
          : queue.items.filter((item) => item.id !== selected.id);
        setQueue((current) => ({
          ...current,
          items: updatedItems,
          total: retainInQueue ? current.total : Math.max(0, current.total - 1),
        }));
        resetEditor(retainInQueue ? updated : updatedItems[0]);
        setReceipt(result);
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : "";
        setError(
          message === "A specific review reason is required for an attributable decision."
            ? "reason_required"
            : message === "Unsupported review decision."
              ? "unsupported_decision"
              : message === "Edited output may only be approved as a new version."
                ? "edited_requires_approval"
                : message === "Edited review output must contain at least 10 characters."
                  ? "finding_too_short"
                  : message.includes("409")
                    ? "version_conflict"
                    : "decision_failed",
        );
      }
    });
  };

  const filterLabels: Array<{ value: ReviewQueueFilter; en: string; ko: string }> = [
    { value: "open", en: "Open", ko: "미처리" },
    { value: "high_attention", en: "High attention", ko: "높은 주의" },
    { value: "all", en: "All", ko: "전체" },
  ];

  return (
    <div className="page-stack review-page">
      <PageGuide
        className="review-page__guide"
        title={{ ko: "검토 콘솔", en: "Review Console" }}
        context={{ ko: "사람 중심 검증", en: "Human assurance" }}
        description={{
          ko: "AI가 도출한 검토 결과를 변경 불가능한 원문 근거와 대조하고, 사유가 포함된 감사 가능한 결정을 기록하는 화면입니다.",
          en: "Compare AI-derived findings with immutable source evidence and record reasoned, attributable review decisions.",
        }}
        actions={(
          <>
            <ModeBadge mode={mode} />
            <div className="queue-badge"><Clock3 size={15} /><strong>{queue.total}</strong> {text("in this view", "현재 보기")}</div>
          </>
        )}
      />

      {receipt ? (
        <section className="review-receipt" role="status" aria-label={text("Review receipt", "검토 처리 영수증")}>
          <CheckCircle2 size={20} />
          <div>
            <strong>{text(
              `Decision recorded · version ${receipt.resultingRevision}`,
              `결정 기록 완료 · 버전 ${receipt.resultingRevision}`,
            )}</strong>
            <span>{text(
              `${receipt.reviewedBy} · ${receipt.contentChanged ? "new edited version retained" : "state decision retained"}`,
              `${receipt.reviewedBy} · ${receipt.contentChanged ? "편집 내용을 새 버전으로 보존" : "상태 결정을 보존"}`,
            )}</span>
          </div>
          <dl>
            <div><dt>{text("Review ID", "검토 ID")}</dt><dd title={receipt.reviewId}>{receipt.reviewId.slice(0, 8)}</dd></div>
            <div><dt>{text("Request ID", "요청 ID")}</dt><dd title={receipt.requestId}>{receipt.requestId.slice(0, 8)}</dd></div>
            <div><dt>{text("Recorded", "기록 시각")}</dt><dd>{formatDate(receipt.reviewedAt, { dateStyle: "medium", timeStyle: "short" }, locale)}</dd></div>
          </dl>
          <button type="button" aria-label={text("Dismiss receipt", "영수증 닫기")} onClick={() => setReceipt(undefined)}><X size={15} /></button>
        </section>
      ) : null}

      {queueError ? (
        <div className="inline-error" role="alert"><CircleAlert size={15} /> {text(
          "The queue could not be refreshed. Your current selection and draft were kept.",
          "대기열을 새로고침하지 못했습니다. 현재 선택과 작성 내용은 그대로 유지했습니다.",
        )}</div>
      ) : null}

      <div className="review-workspace dossier-reveal dossier-reveal--delay-1" aria-busy={pending}>
        <aside className="review-queue">
          <header>
            <div><span>{text("Exception queue", "예외 대기열")}</span><strong>{text(`${queue.total} results`, `${queue.total}건`)}</strong></div>
            <button
              type="button"
              disabled={pending}
              aria-label={text("Refresh queue", "대기열 새로고침")}
              onClick={() => requestAction({ kind: "queue", view, cursor, pageSize: queue.pageSize })}
            ><RotateCcw className={pending ? "is-spinning" : ""} size={15} /></button>
          </header>
          <div className="review-queue__filters">
            {filterLabels.map((filter) => (
              <button
                className={view === filter.value ? "active" : ""}
                key={filter.value}
                type="button"
                disabled={pending}
                aria-pressed={view === filter.value}
                onClick={() => requestAction({ kind: "queue", view: filter.value, pageSize: queue.pageSize })}
              >{text(filter.en, filter.ko)}</button>
            ))}
          </div>
          {visibleItems.length ? (
            <ol>{visibleItems.map((item) => (
              <li key={item.id}>
                <button
                  className={selectedId === item.id ? "active" : ""}
                  type="button"
                  aria-current={selectedId === item.id ? "true" : undefined}
                  aria-pressed={selectedId === item.id}
                  onClick={() => requestAction({ kind: "select", itemId: item.id })}
                >
                  <div className="review-item__top"><span className={`priority-dot priority-dot--${item.priority}`} aria-hidden="true" /> <code>{item.marcsCms}</code><StatusPill state={item.state} /></div>
                  <strong lang="en">{item.company}</strong>
                  <p>{reviewRecordText(item.trigger)}</p>
                  <div className="review-item__version"><span><Layers3 size={11} /> AI v{item.summaryRevision} · {item.documentVersionId.slice(0, 8)}</span>{item.relatedOpenItems > 1 ? <span>{text(`${item.relatedOpenItems} related versions`, `관련 버전 ${item.relatedOpenItems}개`)}</span> : null}</div>
                  <div><span>{item.failedChecks.length ? text(`${item.failedChecks.length} failed ${item.failedChecks.length === 1 ? "check" : "checks"}`, `실패한 검사 ${item.failedChecks.length}건`) : text("Policy review · no failed checks", "정책 검토 · 실패 검사 없음")}</span><time dateTime={item.submittedAt}>{formatDate(item.submittedAt, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }, locale)}</time></div>
                </button>
              </li>
            ))}</ol>
          ) : (
            <div className="review-queue__empty"><Check size={18} /><p>{text("No review items match this view.", "이 보기에 해당하는 검토 항목이 없습니다.")}</p></div>
          )}
          <footer>
            <button
              type="button"
              disabled={pending || !queue.previousCursor}
              onClick={() => requestAction({ kind: "queue", view, cursor: queue.previousCursor, pageSize: queue.pageSize })}
            ><ChevronLeft size={13} /> {text("Previous", "이전")}</button>
            <label><span className="sr-only">{text("Items per page", "페이지당 항목")}</span><select value={queue.pageSize} disabled={pending} onChange={(event) => requestAction({ kind: "queue", view, pageSize: Number(event.target.value) })}><option value="10">10</option><option value="25">25</option><option value="50">50</option></select></label>
            <strong>{queue.page} / {totalPages}</strong>
            <button
              type="button"
              disabled={pending || !queue.nextCursor}
              onClick={() => requestAction({ kind: "queue", view, cursor: queue.nextCursor, pageSize: queue.pageSize })}
            >{text("Next", "다음")} <ChevronRight size={13} /></button>
          </footer>
        </aside>

        {selected ? (
          <section className="review-stage" aria-label={text("Selected review item", "선택된 검토 항목")}>
            <header className="review-stage__header">
              <div><p className="eyebrow">{text("Review item", "검토 항목")} · {selected.marcsCms} · AI v{selected.summaryRevision}</p><h2 lang="en">{selected.company}</h2><p>{reviewRecordText(selected.trigger)}</p></div>
              <Link href={`/drug-letters/${selected.letterId}`}>{text("Open full dossier", "전체 기록 열기")} <ExternalLink size={14} /></Link>
            </header>

            <section className={`failed-checks${!selected.highAttention && !selected.failedChecks.length ? " failed-checks--clear" : ""}`}>
              {selected.highAttention || selected.failedChecks.length ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
              <div><span>{selected.failedChecks.length ? text("Validation exceptions", "검증 예외") : selected.highAttention ? text("Confidence review", "신뢰도 검토") : text("Policy review", "정책 검토")}</span>{selected.failedChecks.length ? <ul>{selected.failedChecks.map((check) => <li key={check}>{reviewRecordText(check)}</li>)}</ul> : <p>{selected.highAttention ? text("No automated check failed. This item remains high attention because its confidence signal is below the review threshold.", "자동 검사에 실패한 항목은 없지만 신뢰도 신호가 검토 기준보다 낮아 높은 주의 상태를 유지합니다.") : text("Automated checks found no exception. Human approval is still required by policy.", "자동 검사 예외는 없지만 정책에 따라 사람의 승인이 필요합니다.")}</p>}</div>
              <div className="confidence-readout">
                <strong>{selected.confidence === null ? text("Not provided", "미제공") : `${Math.round(selected.confidence * 100)}%`}</strong>
                <small>{text("Confidence is separate from the failed-check count.", "신뢰도는 실패 검사 건수와 별도의 지표입니다.")}</small>
              </div>
            </section>

            <div className="review-comparison">
              <section className="review-source">
                <header><div><Quote size={16} /><span>{text("Immutable source evidence · English", "변경 불가능한 원문 증거 · 영어")}</span></div><span className="read-only-badge">{text("Read only", "읽기 전용")}</span></header>
                <div className="review-paper"><p lang="en">{selected.sourceExcerpt}</p><footer><Fingerprint size={14} /><code>#{selected.sourceAnchor}</code></footer></div>
                <div className="source-integrity"><ShieldCheck size={15} /><p>{text(
                  "Excerpt verified against the current normalized source. Source bytes and hashes cannot be changed here.",
                  "발췌문은 현재 정규화된 원문과 대조하여 검증되었습니다. 여기서는 원문 바이트와 해시를 변경할 수 없습니다.",
                )}</p></div>
              </section>
              <section className="review-derived">
                <header><div><FileCheck2 size={16} /><span>{derivedLanguage === "ko" ? text("AI-derived finding · Korean", "AI 도출 지적 사항 · 한국어") : text("AI-derived finding · English", "AI 도출 지적 사항 · 영어")}</span></div><StatusPill state={selected.state} /></header>
                <label><span className="sr-only">{text("Edit derived finding", "도출된 지적 사항 편집")}</span><textarea disabled={!reviewable || pending} lang={derivedLanguage} value={editedFinding} onChange={(event) => setEditedFinding(event.target.value)} /></label>
                <div className="review-taxonomy"><span>{text("Assigned taxonomy · English controlled terms", "지정된 분류 체계 · 영어 통제 용어")}</span>{selected.categories.map((category) => <span key={category}>{category}</span>)}</div>
                <div className="material-change-note"><CircleAlert size={15} /><p>{text(
                  "Approve an edit to retain it as a new derived version. The prior output stays in the audit history.",
                  "편집 내용을 승인하면 새 파생 버전으로 보존되며 이전 출력은 감사 이력에 남습니다.",
                )}</p></div>
              </section>
            </div>

            {reviewable ? (
              <section className="decision-panel">
                <label><span>{text("Decision reason", "결정 사유")} <strong>{text("Required", "필수")}</strong></span><textarea disabled={pending} value={reason} onChange={(event) => setReason(event.target.value)} placeholder={text("State how the source evidence supports the decision, or what must be corrected…", "원문 증거가 결정을 어떻게 뒷받침하는지 또는 무엇을 수정해야 하는지 작성하세요…")} maxLength={2000} /><small>{reason.length}/2,000</small></label>
                {error ? <div className="inline-error" role="alert"><CircleAlert size={15} /> {
                  error === "reason_required" ? text("A specific review reason is required for an attributable decision.", "추적 가능한 결정을 위해 구체적인 검토 사유가 필요합니다.")
                    : error === "unsupported_decision" ? text("Unsupported review decision.", "지원되지 않는 검토 결정입니다.")
                      : error === "edited_requires_approval" ? text("An edited finding must be approved to create its new version. Undo the edit before requesting revision or rejecting.", "편집한 지적 사항은 새 버전을 만들기 위해 승인해야 합니다. 수정 요청이나 거부 전에는 편집을 되돌려 주세요.")
                        : error === "finding_too_short" ? text("Edited output must contain at least 10 characters.", "편집한 출력은 10자 이상이어야 합니다.")
                          : error === "version_conflict" ? text("Another reviewer changed this version. Refresh the queue before deciding.", "다른 검토자가 이 버전을 변경했습니다. 결정하기 전에 대기열을 새로고침하세요.")
                            : text("The service did not confirm this decision. No local review state was changed.", "서비스에서 이 결정을 확인하지 못했습니다. 로컬 검토 상태는 변경하지 않았습니다.")
                }</div> : null}
                <div className="decision-actions"><button className="button button--danger-outline" type="button" disabled={pending} onClick={() => decide("rejected")}><X size={16} /> {text("Reject", "거부")}</button><button className="button button--secondary" type="button" disabled={pending} onClick={() => decide("needs_revision")}><RotateCcw size={16} /> {text("Request revision", "수정 요청")}</button><button className="button button--approve" type="button" disabled={pending} onClick={() => decide("approved")}><CheckCircle2 size={16} /> {pending ? text("Recording…", "기록 중…") : text("Approve grounded output", "근거 있는 출력 승인")}</button></div>
                <p><ShieldCheck size={14} /> {text(
                  "Decision records actor, UTC time, source version, before/after values, reason, review ID, and request ID.",
                  "결정에는 수행자, UTC 시간, 원문 버전, 변경 전후 값, 사유, 검토 ID 및 요청 ID가 기록됩니다.",
                )}</p>
              </section>
            ) : (
              <div className="review-terminal-note"><ShieldCheck size={16} /><p>{text("This version has a terminal decision and is read only. Use its receipt and audit history for traceability.", "이 버전은 최종 결정이 기록되어 읽기 전용입니다. 처리 영수증과 감사 이력으로 추적할 수 있습니다.")}</p></div>
            )}
          </section>
        ) : <section className="empty-state"><FileCheck2 size={24} /><h2>{text("No review item selected.", "선택된 검토 항목이 없습니다.")}</h2><p>{text("Choose another queue view or refresh to look for work.", "다른 대기열 보기를 선택하거나 새로고침하여 검토 항목을 확인하세요.")}</p></section>}
      </div>

      {deferredAction ? (
        <div className="review-dialog-backdrop">
          <section className="review-dialog" role="dialog" aria-modal="true" aria-labelledby="review-unsaved-title">
            <CircleAlert size={22} />
            <div><h2 id="review-unsaved-title">{text("Discard unsaved review changes?", "저장하지 않은 검토 내용을 버릴까요?")}</h2><p>{text("The edited finding or decision reason has not been recorded. Continue editing or discard it before leaving this item.", "편집한 지적 사항이나 결정 사유가 아직 기록되지 않았습니다. 계속 편집하거나 현재 항목을 떠나기 전에 내용을 버리세요.")}</p></div>
            <div><button className="button button--secondary" type="button" onClick={() => setDeferredAction(undefined)}>{text("Continue editing", "계속 편집")}</button><button className="button button--danger-outline" type="button" onClick={() => executeAction(deferredAction)}>{text("Discard and continue", "버리고 계속")}</button></div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
