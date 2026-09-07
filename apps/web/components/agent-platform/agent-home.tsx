"use client";

/* THESIS: A review objective becomes an inspectable workflow, replacing a chat landing.
 * OWN-WORLD: Navy rail, cool white workbench, cobalt selection, orange attribution.
 * STORY: Prepare a brief, inspect responsibilities, then enter governed case work.
 * FIRST VIEWPORT: Objective at left; ordered workflow and step inspector at right.
 * FORM: Multidisciplinary protocol board, grounded candidate 5, seed 8dd383a8.
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleDot,
  Download,
  FileText,
  GitBranch,
  Layers3,
  Save,
  ShieldCheck,
  Users,
  WifiOff,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import {
  agentDefinitions,
  parseReviewDraft,
  REVIEW_DRAFT_KEY,
  reviewTemplates,
  workflowSteps,
  type LocalReviewDraft,
} from "@/lib/agent-workspace";
import { formatCaseStatus, type AgentCase } from "@/lib/case-types";
import styles from "./agent-home.module.css";

type Props = {
  cases: AgentCase[] | null;
  access: "ready" | "unavailable" | "restricted";
};

export function AgentHome({ cases, access }: Props) {
  const { text, locale } = useI18n();
  const router = useRouter();
  const pick = (pair: readonly [string, string]) => text(pair[0], pair[1]);
  const [objective, setObjective] = useState("");
  const [template, setTemplate] = useState<string>("impact");
  const [selectedStep, setSelectedStep] = useState(0);
  const [saved, setSaved] = useState<LocalReviewDraft | null>(null);
  const [notice, setNotice] = useState<
    "saved" | "storage" | "restored" | "cleared" | null
  >(null);
  const objectiveRef = useRef<HTMLTextAreaElement>(null);
  const [caseFilter, setCaseFilter] = useState("all");
  const step = workflowSteps[selectedStep];
  const agent = step.agent === null ? null : agentDefinitions[step.agent];
  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const draft = parseReviewDraft(
          window.localStorage.getItem(REVIEW_DRAFT_KEY),
        );
        if (draft) {
          setObjective(draft.objective);
          setTemplate(draft.template);
          setSaved(draft);
          setNotice("restored");
        }
      } catch {
        setNotice("storage");
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  const dirty = saved?.objective !== objective || saved?.template !== template;
  function selectStep(index: number) {
    setSelectedStep(index);
    if (window.matchMedia("(max-width: 600px)").matches) {
      requestAnimationFrame(() => {
        document.getElementById("step-inspector")?.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
          block: "start",
        });
      });
    }
  }
  function saveDraft(event: React.FormEvent) {
    event.preventDefault();
    if (!objective.trim()) {
      objectiveRef.current?.focus();
      return;
    }
    const draft: LocalReviewDraft = {
      version: 1,
      objective: objective.trim(),
      template,
      updatedAt: new Date().toISOString(),
    };
    try {
      window.localStorage.setItem(REVIEW_DRAFT_KEY, JSON.stringify(draft));
      setSaved(draft);
      setObjective(draft.objective);
      setNotice("saved");
    } catch {
      setNotice("storage");
    }
  }
  function exportDraft() {
    const draft = {
      version: 1,
      objective: objective.trim(),
      template,
      workflow: "regulatory-impact-review@1.0.0",
      state: "LOCAL_DRAFT_NOT_EXECUTED",
      exportedAt: new Date().toISOString(),
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(draft, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "pharmaagent-review-brief.json";
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const visibleCases = cases?.filter(
    (item) =>
      caseFilter === "all" ||
      (caseFilter === "review"
        ? ["AWAITING_PLAN_APPROVAL", "WAITING_FOR_REVIEW"].includes(item.status)
        : ["RUNNING", "READY", "PLANNING"].includes(item.status)),
  );
  return (
    <div className={styles.home}>
      <header className={styles.heading}>
        <div>
          <div className={styles.location}>
            <GitBranch size={15} />
            {text("Agent workspace", "에이전트 워크스페이스")}
          </div>
          <h1>
            {text(
              "Give your next review a plan.",
              "다음 검토를 에이전트와 설계하세요.",
            )}
          </h1>
          <p>
            {text(
              "Define the objective. Inspect the specialists. Keep every decision connected to evidence.",
              "목표를 정하고, 전문가별 작업을 살펴보고, 모든 판단을 근거에 연결하세요.",
            )}
          </p>
        </div>
        <Link className={styles.subtleLink} href="/cases">
          {text("Case workspace", "케이스 워크스페이스")}
          <ArrowRight size={16} />
        </Link>
      </header>
      <div className={styles.workbench}>
        <section className={styles.brief} aria-labelledby="brief-heading">
          <div className={styles.sectionTop}>
            <span className={styles.sectionMark}>
              <FileText size={18} />
            </span>
            <div>
              <h2 id="brief-heading">{text("Review brief", "검토 브리프")}</h2>
              <p>
                {text(
                  "Start with the question that matters.",
                  "확인해야 할 질문부터 시작하세요.",
                )}
              </p>
            </div>
          </div>
          <form onSubmit={saveDraft}>
            <label className={styles.fieldLabel} htmlFor="review-objective">
              {text(
                "What would you like to investigate?",
                "무엇을 검토할까요?",
              )}
            </label>
            <textarea
              ref={objectiveRef}
              id="review-objective"
              value={objective}
              maxLength={3000}
              required
              rows={6}
              onChange={(event) => {
                setObjective(event.target.value);
                setNotice(null);
              }}
              placeholder={text(
                "Describe the warning letter, quality process, or evidence question you want to review…",
                "검토할 경고서한, 품질 프로세스 또는 근거에 관한 질문을 입력하세요…",
              )}
            />
            <div className={styles.inputMeta}>
              <span>
                {text("Saved on this browser only", "이 브라우저에만 저장")}
              </span>
              <span>{objective.length.toLocaleString()} / 3,000</span>
            </div>
            <fieldset className={styles.templates}>
              <legend>
                {text(
                  "Or start from a review prompt",
                  "검토 질문 예시로 시작하기",
                )}
              </legend>
              {reviewTemplates.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={template === item.id && !!objective}
                  onClick={() => {
                    setTemplate(item.id);
                    setObjective(pick(item.objective));
                    setNotice(null);
                    objectiveRef.current?.focus();
                  }}
                >
                  {text(item.en, item.ko)}
                  <ArrowRight size={14} />
                </button>
              ))}
            </fieldset>
            <div className={styles.briefActions}>
              <button
                className={styles.primaryButton}
                type="submit"
                disabled={!objective.trim() || (!dirty && !!saved)}
              >
                <Save size={16} />
                {saved && !dirty
                  ? text("Draft saved", "초안 저장됨")
                  : text("Save review brief", "검토 브리프 저장")}
              </button>
              <button
                className={styles.exportButton}
                type="button"
                disabled={!objective.trim()}
                onClick={exportDraft}
                aria-label={text("Export review brief", "검토 브리프 내보내기")}
                title={text("Export review brief", "검토 브리프 내보내기")}
              >
                <Download size={17} />
              </button>
            </div>
            <div className={styles.notice} aria-live="polite">
              {notice === "saved"
                ? text(
                    "Brief saved locally. No agent run has been started.",
                    "브리프를 브라우저에 저장했습니다. 에이전트 실행은 시작되지 않았습니다.",
                  )
                : notice === "restored"
                  ? text(
                      "Your browser draft has been restored.",
                      "이 브라우저에 저장한 초안을 불러왔습니다.",
                    )
                  : notice === "storage"
                    ? text(
                        "Browser storage is unavailable. Export your brief to keep a copy.",
                        "브라우저 저장소를 사용할 수 없습니다. 브리프를 내보내 보관하세요.",
                      )
                    : notice === "cleared"
                      ? text(
                          "Local draft removed.",
                          "브라우저 초안을 삭제했습니다.",
                        )
                      : text(
                          "Preparing a brief does not create or execute a case.",
                          "브리프 준비만으로 케이스가 생성되거나 실행되지 않습니다.",
                        )}
            </div>
            {saved ? (
              <button
                className={styles.textButton}
                type="button"
                onClick={() => {
                  try {
                    window.localStorage.removeItem(REVIEW_DRAFT_KEY);
                    setSaved(null);
                    setObjective("");
                    setNotice("cleared");
                  } catch {
                    setNotice("storage");
                  }
                }}
              >
                {text("Delete browser draft", "브라우저 초안 삭제")}
              </button>
            ) : null}
          </form>
          <div className={styles.sourceHint}>
            <BookOpen size={18} />
            <div>
              <strong>
                {text("Evidence comes first", "근거부터 연결합니다")}
              </strong>
              <p>
                {text(
                  "A governed case starts with an exact FDA source version. Find the source before assigning work.",
                  "정식 케이스는 정확한 FDA 원문 버전에서 시작합니다. 작업을 배정하기 전에 근거를 선택하세요.",
                )}
              </p>
              <Link href="/drug-letters">
                {text("Find source evidence", "원문 근거 찾기")}
                <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </section>
        <section className={styles.plan} aria-labelledby="workflow-heading">
          <div className={styles.planHeading}>
            <div>
              <div className={styles.definitionLabel}>
                {text("Workflow definition", "워크플로 정의")}
                <span>v1.0.0</span>
              </div>
              <h2 id="workflow-heading">
                {text("Regulatory impact review", "규제 영향 검토")}
              </h2>
            </div>
            <span className={styles.outlineBadge}>
              {text("Not executing", "실행 전")}
            </span>
          </div>
          <p className={styles.planIntro}>
            {text(
              "Five specialists. Two human checkpoints. One traceable review.",
              "다섯 전문 에이전트와 두 차례 사람의 검토를 하나의 흐름으로 연결합니다.",
            )}
          </p>
          <div className={styles.planBody}>
            <ol
              className={styles.steps}
              aria-label={text("Workflow steps", "워크플로 단계")}
            >
              {workflowSteps.map((item, index) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => selectStep(index)}
                    aria-pressed={selectedStep === index}
                    aria-controls="step-inspector"
                    className={
                      selectedStep === index ? styles.selectedStep : undefined
                    }
                  >
                    <span className={styles.stepIcon} data-kind={item.kind}>
                      {item.kind === "human" ? (
                        <Users size={15} />
                      ) : item.kind === "service" ? (
                        <Check size={15} />
                      ) : (
                        <GitBranch size={15} />
                      )}
                    </span>
                    <span>
                      <strong>{pick(item.name)}</strong>
                      <small>
                        {item.agent !== null
                          ? pick(agentDefinitions[item.agent].name)
                          : item.kind === "human"
                            ? text("Human checkpoint", "사람의 검토 지점")
                            : text("Deterministic check", "규칙 기반 처리")}
                      </small>
                    </span>
                    <ChevronRight size={14} />
                  </button>
                  {index < workflowSteps.length - 1 ? (
                    <ArrowDown
                      className={styles.connector}
                      size={12}
                      aria-hidden="true"
                    />
                  ) : null}
                </li>
              ))}
            </ol>
            <aside
              id="step-inspector"
              className={styles.inspector}
              aria-live="polite"
            >
              <a className={styles.mobileBack} href="#workflow-heading">
                {text("Back to workflow steps", "워크플로 단계로 돌아가기")}
              </a>
              <span className={styles.inspectorKind}>
                {step.kind === "agent"
                  ? text("Specialist responsibility", "전문 에이전트 역할")
                  : step.kind === "human"
                    ? text("Human decision", "사람의 판단")
                    : text("Deterministic service", "규칙 기반 서비스")}
              </span>
              <h3>{agent ? pick(agent.name) : pick(step.name)}</h3>
              <p>
                {agent
                  ? pick(agent.role)
                  : step.kind === "human"
                    ? text(
                        "An authorized reviewer inspects the bound record and records an independent decision before work proceeds.",
                        "권한이 있는 검토자가 연결된 기록을 확인하고 독립적인 판단을 기록해야 다음 작업으로 진행합니다.",
                      )
                    : text(
                        "A defined service checks or assembles the retained records. This step does not make an autonomous regulatory decision.",
                        "정해진 서비스가 보존된 기록을 검증하거나 구성합니다. 이 단계에서 규제 판단을 자율적으로 내리지 않습니다.",
                      )}
              </p>
              <dl>
                <div>
                  <dt>{text("Receives", "입력")}</dt>
                  <dd>
                    {agent
                      ? pick(agent.input)
                      : text(
                          "Version-bound output from the preceding step",
                          "이전 단계의 버전이 고정된 결과",
                        )}
                  </dd>
                </div>
                <div>
                  <dt>{text("Produces", "출력")}</dt>
                  <dd>{pick(step.output)}</dd>
                </div>
                {agent ? (
                  <div>
                    <dt>{text("Tools & scope", "도구와 범위")}</dt>
                    <dd>{pick(agent.tools)}</dd>
                  </div>
                ) : null}
              </dl>
              <div className={styles.inspectorFooter}>
                <ShieldCheck size={16} />
                <span>
                  {text(
                    "Human decisions remain separate from agent outputs.",
                    "사람의 판단과 에이전트 결과는 구분하여 기록합니다.",
                  )}
                </span>
              </div>
              <Link href="/agents">
                {text("Explore the agent team", "에이전트 팀 살펴보기")}
                <ArrowRight size={14} />
              </Link>
            </aside>
          </div>
        </section>
      </div>
      <section className={styles.caseSection} aria-labelledby="case-heading">
        <div className={styles.caseHeading}>
          <div>
            <h2 id="case-heading">{text("Review activity", "검토 활동")}</h2>
            <p>
              {text(
                "Cases and execution records from your accessible workspace.",
                "접근 가능한 워크스페이스의 케이스와 실행 기록입니다.",
              )}
            </p>
          </div>
          <Link className={styles.subtleLink} href="/cases">
            {text("All cases", "전체 케이스")}
            <ArrowRight size={15} />
          </Link>
        </div>
        <div
          className={styles.caseToolbar}
          role="group"
          aria-label={text("Filter review activity", "검토 활동 필터")}
        >
          {[
            ["all", "All activity", "전체 활동"],
            ["active", "In progress", "진행 중"],
            ["review", "Needs review", "검토 필요"],
          ].map(([value, en, ko]) => (
            <button
              key={value}
              type="button"
              aria-pressed={caseFilter === value}
              onClick={() => setCaseFilter(value)}
            >
              {text(en, ko)}
            </button>
          ))}
        </div>
        {access !== "ready" ? (
          <div className={styles.unavailable}>
            <WifiOff size={22} />
            <div>
              <h3>
                {access === "restricted"
                  ? text(
                      "Case records require additional access",
                      "케이스 기록에 대한 추가 권한이 필요합니다",
                    )
                  : text(
                      "Live workspace is not connected yet",
                      "실시간 워크스페이스가 아직 연결되지 않았습니다",
                    )}
              </h3>
              <p>
                {text(
                  "You can prepare a local brief and inspect the workflow. Live cases, source retrieval, and agent execution are not available in this view.",
                  "브라우저에서 브리프를 준비하고 워크플로를 살펴볼 수 있습니다. 현재 화면에서 실시간 케이스, 원문 검색, 에이전트 실행은 사용할 수 없습니다.",
                )}
              </p>
            </div>
            <button type="button" onClick={() => router.refresh()}>
              {text("Check connection", "연결 확인")}
            </button>
          </div>
        ) : visibleCases?.length ? (
          <div className={styles.caseList}>
            {visibleCases.slice(0, 5).map((item) => (
              <Link key={item.id} href={`/cases/${item.id}`}>
                <CircleDot size={18} />
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.objective}</small>
                </span>
                <span>{formatCaseStatus(item.status)}</span>
                <time dateTime={item.updatedAt}>
                  {new Intl.DateTimeFormat(locale, {
                    month: "short",
                    day: "numeric",
                  }).format(new Date(item.updatedAt))}
                </time>
                <ArrowRight size={16} />
              </Link>
            ))}
          </div>
        ) : (
          <div className={styles.unavailable}>
            <Layers3 size={24} />
            <div>
              <h3>
                {text(
                  "No cases in this view",
                  "이 보기에 표시할 케이스가 없습니다",
                )}
              </h3>
              <p>
                {text(
                  "Choose another filter or open the case workspace to inspect available records.",
                  "다른 필터를 선택하거나 케이스 워크스페이스에서 기록을 확인하세요.",
                )}
              </p>
            </div>
          </div>
        )}
      </section>
      <footer className={styles.homeFooter}>
        <span>PharmaAgent OS</span>
        <p>
          {text(
            "Agent-assisted research. Evidence-backed review. Human decisions.",
            "에이전트가 돕는 조사, 근거에 기반한 검토, 사람이 내리는 판단.",
          )}
        </p>
        <Link href="/ask">
          {text("Open research chat", "리서치 대화 열기")}
          <ArrowRight size={14} />
        </Link>
      </footer>
    </div>
  );
}
