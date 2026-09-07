"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  Download,
  FileText,
  GitBranch,
  HelpCircle,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";
import {
  agentDefinitions,
  REVIEW_DRAFT_KEY,
  reviewTemplates,
  workflowSteps,
} from "@/lib/agent-workspace";
import {
  MAX_REQUESTS,
  readRequests,
  REQUESTS_KEY,
  requestText,
  validFdaUrl,
  type ReviewRequest,
} from "@/lib/review-requests";
import { formatCaseStatus, type AgentCase } from "@/lib/case-types";
import styles from "./agent-home.module.css";

const choices = [
  {
    id: "evidence",
    en: "Understand a warning letter",
    ko: "경고서한 핵심 파악",
    detail: [
      "Key findings and their source passages",
      "주요 지적 사항과 원문 근거 정리",
    ],
  },
  {
    id: "impact",
    en: "Review the possible impact",
    ko: "우리 업무 영향 검토",
    detail: [
      "Questions relevant to our quality work",
      "우리 품질 업무에서 확인할 사항 정리",
    ],
  },
  {
    id: "process",
    en: "Compare with a procedure",
    ko: "내부 절차와 비교",
    detail: [
      "Connections and gaps to check with a reviewer",
      "내부 절차와의 연관성 및 추가 확인 사항",
    ],
  },
] as const;

export function AgentHome({
  cases,
  access,
}: {
  cases: AgentCase[] | null;
  access: "ready" | "unavailable" | "restricted";
}) {
  const { text, locale } = useI18n();
  const pick = (pair: readonly [string, string]) => text(pair[0], pair[1]);
  const [template, setTemplate] = useState("evidence");
  const [objective, setObjective] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [requests, setRequests] = useState<ReviewRequest[]>([]);
  const [saved, setSaved] = useState<ReviewRequest | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [storageError, setStorageError] = useState(false);
  const [error, setError] = useState<"question" | "url" | "limit" | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const sourceRef = useRef<HTMLInputElement>(null);
  const sourceDetailsRef = useRef<HTMLDetailsElement>(null);
  const receiptRef = useRef<HTMLHeadingElement>(null);
  const dirty = saved
    ? saved.objective !== objective ||
      saved.template !== template ||
      saved.sourceUrl !== sourceUrl
    : !!objective || !!sourceUrl;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        setRequests(
          readRequests(
            localStorage.getItem(REQUESTS_KEY),
            localStorage.getItem(REVIEW_DRAFT_KEY),
          ),
        );
      } catch {
        setStorageError(true);
      }
      setLoaded(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    const guardNavigation = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest<HTMLAnchorElement>("a[href]");
      if (!link || link.target === "_blank" || link.hasAttribute("download"))
        return;
      const destination = new URL(link.href, window.location.href);
      if (
        destination.pathname === window.location.pathname &&
        destination.search === window.location.search
      )
        return;
      if (
        !window.confirm(
          text(
            "Leave this page and discard your unsaved changes?",
            "저장하지 않은 변경 내용을 버리고 다른 페이지로 이동할까요?",
          ),
        )
      ) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", guardNavigation, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", guardNavigation, true);
    };
  }, [dirty, text]);

  function currentRequest(): ReviewRequest {
    return {
      id: editingId ?? crypto.randomUUID(),
      template,
      objective: objective.trim(),
      sourceUrl: sourceUrl.trim(),
      updatedAt: new Date().toISOString(),
    };
  }
  function validate() {
    if (!objective.trim()) {
      setError("question");
      questionRef.current?.focus();
      return false;
    }
    if (!validFdaUrl(sourceUrl)) {
      setError("url");
      if (sourceDetailsRef.current) sourceDetailsRef.current.open = true;
      sourceRef.current?.focus();
      return false;
    }
    setError(null);
    return true;
  }
  function save(event: React.FormEvent) {
    event.preventDefault();
    if (!validate()) return;
    const draft = currentRequest();
    try {
      const latest = readRequests(
        localStorage.getItem(REQUESTS_KEY),
        localStorage.getItem(REVIEW_DRAFT_KEY),
      );
      const remaining = latest.filter((item) => item.id !== draft.id);
      if (remaining.length >= MAX_REQUESTS) {
        setError("limit");
        return;
      }
      const next = [draft, ...remaining];
      localStorage.setItem(REQUESTS_KEY, JSON.stringify(next));
      setRequests(next);
      setSaved(draft);
      setEditingId(draft.id);
      setObjective(draft.objective);
      setSourceUrl(draft.sourceUrl);
      setStorageError(false);
      setMessage(
        text(
          "Request draft saved on this device.",
          "이 기기에 검토 요청 초안을 저장했습니다.",
        ),
      );
      requestAnimationFrame(() => receiptRef.current?.focus());
    } catch {
      setStorageError(true);
    }
  }
  function download(json = false, draft = currentRequest()) {
    if (!validate()) return;
    const content = json
      ? JSON.stringify(
          {
            ...draft,
            state: "LOCAL_DRAFT_NOT_EXECUTED",
            workflow: "regulatory-impact-review@1.0.0",
          },
          null,
          2,
        )
      : requestText(draft, locale === "ko");
    const url = URL.createObjectURL(
      new Blob([content], {
        type: json ? "application/json" : "text/plain;charset=utf-8",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `pharmaagent-request.${json ? "json" : "txt"}`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function canLeave() {
    return (
      !dirty ||
      window.confirm(
        text(
          "Discard the changes you have not saved?",
          "저장하지 않은 변경 내용을 버릴까요?",
        ),
      )
    );
  }
  function edit(draft?: ReviewRequest) {
    if (!canLeave()) return;
    setTemplate(draft?.template ?? "evidence");
    setObjective(draft?.objective ?? "");
    setSourceUrl(draft?.sourceUrl ?? "");
    setEditingId(draft?.id ?? null);
    setSaved(draft ?? null);
    setError(null);
    setMessage("");
    questionRef.current?.focus();
  }
  function remove(id: string) {
    try {
      const next = readRequests(
        localStorage.getItem(REQUESTS_KEY),
        localStorage.getItem(REVIEW_DRAFT_KEY),
      ).filter((item) => item.id !== id);
      localStorage.setItem(REQUESTS_KEY, JSON.stringify(next));
      setRequests(next);
      setDeleting(null);
      if (editingId === id) {
        setSaved(null);
        setEditingId(null);
      }
      setMessage(
        text(
          "Saved draft deleted. Any text in the editor is still available.",
          "저장한 초안을 삭제했습니다. 작성 중인 입력 내용은 유지됩니다.",
        ),
      );
    } catch {
      setStorageError(true);
    }
  }
  const chosen = choices.find((item) => item.id === template)!;
  return (
    <div className={styles.home}>
      <header className={styles.heading}>
        <div>
          <p className={styles.eyebrow}>
            {text(
              "Daewoong · Regulatory review assistant",
              "대웅 · 규제 검토 도우미",
            )}
          </p>
          <h1>
            {text(
              "What would you like to review?",
              "어떤 검토를 도와드릴까요?",
            )}
          </h1>
          <p>
            {text(
              "Prepare a review of FDA findings, one question at a time.",
              "FDA 지적 사항부터 우리 업무 영향까지, 검토할 질문을 정리해보세요.",
            )}
          </p>
        </div>
        <Link href="/help" className={styles.helpLink}>
          <HelpCircle size={18} />
          {text("How to use this", "처음 이용하시나요?")}
        </Link>
      </header>

      <div className={styles.availability}>
        <span className={styles.stateDot} aria-hidden="true" />
        <div>
          <strong>
            {text(
              "Request drafts are available",
              "지금은 검토 요청을 준비할 수 있어요",
            )}
          </strong>
          <p>
            {text(
              "Save and download your request now. Automated analysis and company-wide sharing are not available yet.",
              "요청을 작성하고 저장·다운로드할 수 있습니다. 자동 분석과 사내 공유 기능은 아직 준비 중입니다.",
            )}
          </p>
        </div>
        <Link href="/help#availability">
          {text("What’s available", "이용 가능 기능")}
          <ArrowRight size={16} />
        </Link>
      </div>

      <div className={styles.workspace}>
        <section className={styles.editor} aria-labelledby="request-heading">
          <div className={styles.sectionHeading}>
            <h2 id="request-heading">
              {editingId
                ? text("Edit your request", "검토 요청 수정")
                : text("Prepare a review request", "검토 요청 작성")}
            </h2>
            {editingId ? (
              <button
                type="button"
                className={styles.textButton}
                onClick={() => edit()}
              >
                <Plus size={16} />
                {text("New request", "새 요청")}
              </button>
            ) : (
              <span>
                {text("No agent setup needed", "에이전트 설정 없이 시작")}
              </span>
            )}
          </div>
          <form onSubmit={save} noValidate>
            <fieldset className={styles.tasks}>
              <legend>
                <span>1</span>
                {text("Choose your task", "하고 싶은 일을 선택하세요")}
              </legend>
              <div className={styles.taskOptions}>
                {choices.map((choice) => (
                  <label
                    key={choice.id}
                    className={
                      template === choice.id ? styles.selectedTask : undefined
                    }
                  >
                    <input
                      type="radio"
                      name="review-type"
                      value={choice.id}
                      checked={template === choice.id}
                      onChange={() => {
                        setTemplate(choice.id);
                        setMessage("");
                      }}
                    />
                    <span>
                      <strong>{text(choice.en, choice.ko)}</strong>
                    </span>
                  </label>
                ))}
              </div>
              <p className={styles.taskDescription}>{pick(chosen.detail)}</p>
            </fieldset>
            <div className={styles.questionHeading}>
              <label htmlFor="review-objective">
                <span>2</span>
                {text("What do you want to find out?", "무엇이 궁금한가요?")}
              </label>
              {!objective ? (
                <button
                  type="button"
                  className={styles.textButton}
                  onClick={() => {
                    const example = reviewTemplates.find(
                      (item) => item.id === template,
                    )!;
                    setObjective(pick(example.objective));
                    setError(null);
                    questionRef.current?.focus();
                  }}
                >
                  {text("Use an example", "예시로 시작")}
                </button>
              ) : null}
            </div>
            <p id="question-help" className={styles.fieldHint}>
              {text(
                "Include the company, topic, or process you want to review. A short question is enough.",
                "회사명, 관심 주제 또는 검토할 업무를 적어주세요. 짧은 질문도 괜찮습니다.",
              )}
            </p>
            <textarea
              ref={questionRef}
              id="review-objective"
              value={objective}
              maxLength={3000}
              rows={4}
              required
              aria-invalid={error === "question"}
              aria-describedby={
                error === "question"
                  ? "question-help question-error"
                  : "question-help"
              }
              placeholder={text(
                "e.g. What should our quality team check after reading this warning letter?",
                "예: 이 경고서한을 보고 우리 품질팀이 확인해야 할 사항은 무엇인가요?",
              )}
              onChange={(event) => {
                setObjective(event.target.value);
                setError(null);
                setMessage("");
              }}
            />
            <div className={styles.fieldMeta}>
              <span>
                {text(
                  dirty ? "Unsaved changes" : "Drafts stay on this device",
                  dirty
                    ? "아직 저장하지 않은 내용이 있습니다"
                    : "초안은 이 기기에만 저장됩니다",
                )}
              </span>
              <span>{objective.length.toLocaleString()} / 3,000</span>
            </div>
            {error === "question" ? (
              <p id="question-error" className={styles.error} role="alert">
                {text(
                  "Enter a question, or use the example to get started.",
                  "질문을 입력하거나 ‘예시로 시작’을 눌러주세요.",
                )}
              </p>
            ) : null}
            <details ref={sourceDetailsRef} className={styles.source}>
              <summary>
                {text("Add an FDA source link", "FDA 원문 링크 추가")}{" "}
                <span>{text("Optional", "선택")}</span>
                <ChevronDown size={16} />
              </summary>
              <label htmlFor="source-url">
                {text("FDA webpage address", "FDA 웹페이지 주소")}
              </label>
              <input
                ref={sourceRef}
                id="source-url"
                type="url"
                value={sourceUrl}
                maxLength={2000}
                placeholder="https://www.fda.gov/…"
                aria-invalid={error === "url"}
                aria-describedby="source-help"
                onChange={(event) => {
                  setSourceUrl(event.target.value);
                  setError(null);
                  setMessage("");
                }}
              />
              <p
                id="source-help"
                className={error === "url" ? styles.error : styles.fieldHint}
              >
                {error === "url"
                  ? text(
                      "Use an HTTPS link from fda.gov, or leave this blank.",
                      "fda.gov의 HTTPS 주소를 입력하거나 비워두세요.",
                    )
                  : text(
                      "The link is saved with your request. Its content is not imported or analyzed yet.",
                      "링크를 요청과 함께 저장합니다. 원문을 가져오거나 분석하지는 않습니다.",
                    )}
              </p>
            </details>
            {error === "limit" ? (
              <p className={styles.error} role="alert">
                {text(
                  "This device holds 30 drafts. Download and remove an older draft to save another.",
                  "이 기기에 초안 30개가 저장되어 있습니다. 기존 초안을 다운로드하고 삭제한 뒤 저장해주세요.",
                )}
              </p>
            ) : null}
            <div className={styles.formActions}>
              <button
                className={styles.primaryButton}
                type="submit"
                disabled={!loaded || (!!saved && !dirty)}
              >
                <Save size={18} />
                {saved && !dirty
                  ? text("Draft saved", "초안 저장됨")
                  : text("Save request draft", "검토 요청 초안 저장")}
              </button>
              <button
                className={styles.secondaryButton}
                type="button"
                disabled={!objective.trim()}
                onClick={() => download()}
              >
                <Download size={18} />
                {text("Download", "다운로드")}
              </button>
            </div>
            <p className={styles.fieldHint}>
              {text(
                "Saving prepares a request. It does not submit it or start an AI analysis.",
                "저장하면 요청 초안이 만들어집니다. 제출되거나 AI 분석이 시작되지는 않습니다.",
              )}
            </p>
          </form>
          {storageError ? (
            <div className={styles.storageError} role="alert">
              <strong>
                {text(
                  "Saved drafts are unavailable",
                  "초안 저장소를 이용할 수 없습니다",
                )}
              </strong>
              <p>
                {text(
                  "The browser could not read or save your drafts. Your question is still here. Download it to keep a copy; existing saved data has not been overwritten.",
                  "브라우저에서 초안을 읽거나 저장할 수 없습니다. 입력한 질문은 유지되니 다운로드로 보관해주세요. 기존 저장 데이터는 덮어쓰지 않았습니다.",
                )}
              </p>
              <button
                className={styles.secondaryButton}
                disabled={!objective.trim()}
                onClick={() => download()}
              >
                {text("Download my request", "요청 다운로드")}
              </button>
            </div>
          ) : null}
          <p className={styles.announcement} role="status">
            {message}
          </p>
          {saved && !dirty ? (
            <section className={styles.receipt} aria-labelledby="saved-heading">
              <h3 ref={receiptRef} tabIndex={-1} id="saved-heading">
                <Check size={20} />
                {text(
                  "Your request is ready to keep",
                  "검토 요청 초안을 준비했어요",
                )}
              </h3>
              <p>
                {text(
                  "It is saved on this device. Download a copy to share through your usual company channels.",
                  "이 기기에 저장되었습니다. 다운로드한 파일은 평소 사용하는 사내 채널로 전달할 수 있습니다.",
                )}
              </p>
              <dl>
                <div>
                  <dt>{text("Task", "검토 유형")}</dt>
                  <dd>{text(chosen.en, chosen.ko)}</dd>
                </div>
                <div>
                  <dt>{text("Question", "검토 질문")}</dt>
                  <dd>{saved.objective}</dd>
                </div>
              </dl>
              <p className={styles.fieldHint}>
                {text(
                  "Next: once source access and analysis are enabled, the request can be used to prepare a formal review.",
                  "다음 단계: 자료 조회와 분석 기능이 준비되면 이 요청을 바탕으로 정식 검토를 진행할 수 있습니다.",
                )}
              </p>
              <details>
                <summary>{text("Technical export", "기술용 내보내기")}</summary>
                <button
                  type="button"
                  className={styles.textButton}
                  onClick={() => download(true, saved)}
                >
                  {text("Download JSON", "JSON 다운로드")}
                </button>
              </details>
            </section>
          ) : null}
        </section>

        <aside className={styles.guide} aria-labelledby="guide-heading">
          <span className={styles.guideIcon}>
            <GitBranch size={24} />
          </span>
          <h2 id="guide-heading">
            {text(
              "You ask. The agents organize the review.",
              "질문은 간단하게, 검토는 에이전트와 함께.",
            )}
          </h2>
          <p>
            {text(
              "When analysis is enabled, the specialists work through these steps. You remain in charge of the decision.",
              "분석 기능이 준비되면 전문 에이전트가 아래 순서로 검토를 돕습니다. 최종 판단은 담당자가 합니다.",
            )}
          </p>
          <ol className={styles.outcomes}>
            <li>
              <BookOpen size={21} />
              <div>
                <strong>
                  {text("Find the source evidence", "원문 근거 확인")}
                </strong>
                <p>
                  {text(
                    "Relevant findings with links back to the FDA source.",
                    "FDA 원문에서 관련 지적 사항과 근거를 확인합니다.",
                  )}
                </p>
              </div>
            </li>
            <li>
              <GitBranch size={21} />
              <div>
                <strong>
                  {text("Connect it to your question", "우리 업무와 연결")}
                </strong>
                <p>
                  {text(
                    "Potential implications and information that still needs checking.",
                    "업무에 미칠 수 있는 영향과 추가 확인 사항을 정리합니다.",
                  )}
                </p>
              </div>
            </li>
            <li>
              <ShieldCheck size={21} />
              <div>
                <strong>
                  {text("Prepare for human review", "담당자 검토 준비")}
                </strong>
                <p>
                  {text(
                    "A source-linked package for a reviewer to verify and decide.",
                    "담당자가 근거를 확인하고 판단할 검토 자료를 준비합니다.",
                  )}
                </p>
              </div>
            </li>
          </ol>
          <details className={styles.workflow}>
            <summary>
              {text(
                "See the detailed agent steps",
                "에이전트 작업 단계 자세히 보기",
              )}
              <ChevronDown size={17} />
            </summary>
            <p>
              {text(
                "Planned workflow · No analysis is running",
                "예정된 검토 절차 · 현재 실행 중인 분석 없음",
              )}
            </p>
            <ol>
              {workflowSteps.map((step) => (
                <li key={step.id}>
                  <strong>{pick(step.name)}</strong>
                  <span>
                    {step.agent === null
                      ? step.kind === "human"
                        ? text("Reviewer", "검토 담당자")
                        : text("System check", "시스템 확인")
                      : pick(agentDefinitions[step.agent].name)}
                  </span>
                  <small>
                    {text("Output: ", "결과: ")}
                    {pick(step.output)}
                  </small>
                </li>
              ))}
            </ol>
            <Link href="/agents">
              {text("Meet the specialist agents", "전문 에이전트 알아보기")}
              <ArrowRight size={16} />
            </Link>
          </details>
          <Link href="/help" className={styles.guideHelp}>
            {text("Read the getting-started guide", "처음 사용하기 안내")}
            <ArrowRight size={17} />
          </Link>
        </aside>
      </div>

      <section
        className={styles.savedSection}
        id="saved-requests"
        aria-labelledby="drafts-heading"
      >
        <div className={styles.sectionHeading}>
          <div>
            <h2 id="drafts-heading">
              {text("Continue a saved request", "저장한 요청 이어서 작성")}
            </h2>
            <p>
              {text(
                "Only drafts saved in this browser appear here. They are not shared company records.",
                "이 브라우저에 저장한 초안만 표시됩니다. 회사 공용 기록에는 저장되지 않습니다.",
              )}
            </p>
          </div>
          <span>
            {storageError
              ? text("Storage unavailable", "저장소 확인 필요")
              : `${requests.length}${text(requests.length === 1 ? " draft" : " drafts", "개 초안")}`}
          </span>
        </div>
        {!loaded ? (
          <p>{text("Loading your drafts…", "저장한 초안을 불러오는 중…")}</p>
        ) : storageError && !requests.length ? (
          <p>
            {text(
              "We could not read your saved drafts. They have not been overwritten.",
              "저장한 초안을 읽을 수 없습니다. 기존 데이터는 덮어쓰지 않았습니다.",
            )}
          </p>
        ) : requests.length ? (
          <ul className={styles.drafts}>
            {requests.map((draft) => (
              <li key={draft.id}>
                <FileText size={22} />
                <button
                  className={styles.draftOpen}
                  onClick={() => edit(draft)}
                >
                  <strong>{draft.objective}</strong>
                  <span>
                    {text(
                      choices.find((item) => item.id === draft.template)!.en,
                      choices.find((item) => item.id === draft.template)!.ko,
                    )}{" "}
                    ·{" "}
                    {new Intl.DateTimeFormat(locale, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    }).format(new Date(draft.updatedAt))}
                  </span>
                </button>
                <button
                  className={styles.iconButton}
                  aria-label={text(
                    `Delete draft: ${draft.objective.slice(0, 50)}`,
                    `초안 삭제: ${draft.objective.slice(0, 50)}`,
                  )}
                  onClick={() => setDeleting(draft.id)}
                >
                  <Trash2 size={18} />
                </button>
                {deleting === draft.id ? (
                  <div className={styles.deleteConfirm}>
                    <span>
                      {text(
                        "Delete this saved draft?",
                        "이 저장 초안을 삭제할까요?",
                      )}
                    </span>
                    <button onClick={() => remove(draft.id)}>
                      {text("Delete", "삭제")}
                    </button>
                    <button onClick={() => setDeleting(null)}>
                      {text("Cancel", "취소")}
                    </button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <div className={styles.empty}>
            <FileText size={25} />
            <div>
              <strong>
                {text(
                  "Your first request starts above",
                  "위에서 첫 검토 요청을 작성해보세요",
                )}
              </strong>
              <p>
                {text(
                  "Save a draft and return here to continue it later.",
                  "초안을 저장하면 여기에서 다시 이어서 작성할 수 있습니다.",
                )}
              </p>
            </div>
          </div>
        )}
      </section>
      {access === "ready" && cases && cases.length > 0 ? (
        <section className={styles.savedSection}>
          <div className={styles.sectionHeading}>
            <h2>{text("Team review records", "팀 검토 기록")}</h2>
            <Link href="/cases">{text("See all", "전체 보기")}</Link>
          </div>
          <ul className={styles.drafts}>
            {cases.slice(0, 5).map((item) => (
              <li key={item.id}>
                <Link href={`/cases/${item.id}`} className={styles.draftOpen}>
                  <strong>{item.title}</strong>
                  <span>{formatCaseStatus(item.status)}</span>
                </Link>
                <ArrowRight size={18} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <footer className={styles.footer}>
        <span>
          <ShieldCheck size={17} />
          {text(
            "AI supports the review. People make the decision.",
            "AI는 검토를 돕고, 최종 판단은 사람이 합니다.",
          )}
        </span>
        <Link href="/help#availability">
          {text("Service availability", "서비스 이용 안내")}
        </Link>
      </footer>
    </div>
  );
}
