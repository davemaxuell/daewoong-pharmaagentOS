"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  CheckCircle2,
  CircleDot,
  Copy,
  ExternalLink,
  FileSearch,
  Languages,
  Link2,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
  TimerReset,
  WandSparkles,
} from "lucide-react";
import { type KeyboardEvent, type ReactNode, useMemo, useRef, useState } from "react";
import { PageGuide } from "@/components/page-guide";
import { LetterBookmarkButton } from "@/components/letter-bookmark-button";
import { formatDate, StatusPill } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import type {
  AiLetterFinding,
  Letter,
  LetterAiArtifact,
  LetterAiArtifactLanguage,
  LetterAiArtifactType,
  OriginalSection,
  TranslatedLetterSection,
} from "@/lib/types";

const contentTabs = ["Original", "Findings", "Summary"] as const;
type ContentTab = (typeof contentTabs)[number];
type AnalysisArtifactType = Exclude<LetterAiArtifactType, "translation">;
type GenerationKey = "translation" | `${AnalysisArtifactType}:${LetterAiArtifactLanguage}`;

const artifactKey = (
  artifactType: LetterAiArtifactType,
  language: LetterAiArtifactLanguage,
) => `${artifactType}:${language}`;

const generationKey = (
  artifactType: LetterAiArtifactType,
  language: LetterAiArtifactLanguage,
): GenerationKey => artifactType === "translation" ? "translation" : `${artifactType}:${language}`;

class ArtifactRequestError extends Error {
  constructor(readonly requestId?: string) {
    super("Artifact generation failed");
  }
}

const tabLabels: Record<ContentTab, { en: string; ko: string }> = {
  Original: { en: "Original", ko: "원문" },
  Findings: { en: "Findings", ko: "지적사항" },
  Summary: { en: "Internal Comparison", ko: "내부 비교" },
};

function RichParagraph({ children, lang }: { children: string; lang: "en" | "ko" }) {
  const fragments = children.split(/(\*\*[^*]+\*\*)/g);
  return (
    <p lang={lang}>
      {fragments.map((fragment, index) => fragment.startsWith("**") && fragment.endsWith("**")
        ? <strong key={`${fragment}-${index}`}>{fragment.slice(2, -2)}</strong>
        : fragment)}
    </p>
  );
}

function ArtifactNotice({ artifact }: { artifact: LetterAiArtifact }) {
  const { locale, text } = useI18n();
  const languageLabel = artifact.language === "ko"
    ? text("Korean", "한국어")
    : text("English", "영어");
  return (
    <div className="ai-artifact-notice">
      <span className="ai-artifact-notice__state">
        <CheckCircle2 size={15} aria-hidden="true" />
        {text("Validated and saved", "검증 및 저장 완료")}
      </span>
      <span className="ai-artifact-notice__language">{languageLabel}</span>
      <span>
        {artifact.createdAt
          ? formatDate(artifact.createdAt, { day: "2-digit", month: "short", year: "numeric" }, locale)
          : text("Current source version", "현재 원문 버전")}
      </span>
      <span className="ai-artifact-notice__provenance" title={`${artifact.modelId} · ${artifact.promptVersion}`}>
        {text("Version-bound", "원문 버전 연계")}
      </span>
    </div>
  );
}

function GeneratePanel({
  type,
  pendingLanguages,
  errors,
  onGenerate,
}: {
  type: AnalysisArtifactType;
  pendingLanguages: Set<LetterAiArtifactLanguage>;
  errors: Partial<Record<LetterAiArtifactLanguage, string>>;
  onGenerate: (language: LetterAiArtifactLanguage) => void;
}) {
  const { text } = useI18n();
  const isFindings = type === "findings";
  const actionLabel = (language: LetterAiArtifactLanguage) => {
    if (pendingLanguages.has(language)) {
      return language === "ko"
        ? text("Generating Korean…", "한국어 생성 중…")
        : text("Generating English…", "영어 생성 중…");
    }
    if (language === "ko") {
      return isFindings
        ? text("Generate findings in Korean", "한국어 지적사항 생성")
        : text("Generate internal comparison in Korean", "한국어 내부 비교 생성");
    }
    return isFindings
      ? text("Generate findings", "영어 지적사항 생성")
      : text("Generate internal comparison", "영어 내부 비교 생성");
  };
  return (
    <section className="ai-generate-panel" aria-busy={pendingLanguages.size > 0}>
      <span className="ai-generate-panel__icon" aria-hidden="true">
        {isFindings ? <FileSearch size={25} /> : <Sparkles size={25} />}
      </span>
      <div className="ai-generate-panel__copy">
        <p className="eyebrow">{text("Choose output language", "출력 언어 선택")}</p>
        <h2>{isFindings
          ? text("Generate clean findings from the full letter", "경고서한 전체에서 핵심 지적사항 생성")
          : text("Generate an internal comparison brief", "내부 비교 브리프 생성")}</h2>
        <p>{isFindings
          ? text(
              "AI reads the complete current source, extracts the findings, and validates every source anchor before the result is saved.",
              "AI가 현재 원문 전체를 읽고 지적사항을 추출한 뒤, 원문 앵커를 검증하여 결과를 저장합니다.",
            )
          : text(
              "The saved analysis highlights what Daewoong teams should compare with their own systems and workflows without making a compliance conclusion.",
              "저장된 분석은 컴플라이언스 결론을 내리지 않으며, 대웅 팀이 자체 시스템과 업무 절차에서 비교할 부분을 안내합니다.",
            )}</p>
        <p className="ai-generate-panel__parallel-note">
          <TimerReset size={15} aria-hidden="true" />
          {text(
            "Runs in the background on this page. You can start another language or artifact while it works.",
            "이 페이지에서 백그라운드로 실행됩니다. 기다리는 동안 다른 언어나 분석을 함께 시작할 수 있습니다.",
          )}
        </p>
      </div>
      <div className="ai-generate-panel__actions">
        {(["en", "ko"] as const).map((language) => {
          const pending = pendingLanguages.has(language);
          return (
            <div key={language} className="ai-generate-choice">
              <button
                className={`button ${language === "ko" ? "button--primary" : "button--secondary"}`}
                type="button"
                disabled={pending}
                onClick={() => onGenerate(language)}
              >
                {pending ? <LoaderCircle className="spin" size={17} /> : <WandSparkles size={17} />}
                <span><small>{language === "ko" ? "한국어" : "English"}</small>{actionLabel(language)}</span>
              </button>
              {errors[language] ? (
                <p className="ai-artifact-error" role="alert">
                  <AlertTriangle size={15} /> {errors[language]}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ArtifactLanguageControls({
  type,
  currentLanguage,
  availableLanguages,
  pendingLanguages,
  onSelect,
  onGenerate,
}: {
  type: AnalysisArtifactType;
  currentLanguage: LetterAiArtifactLanguage;
  availableLanguages: Set<LetterAiArtifactLanguage>;
  pendingLanguages: Set<LetterAiArtifactLanguage>;
  onSelect: (language: LetterAiArtifactLanguage) => void;
  onGenerate: (language: LetterAiArtifactLanguage) => void;
}) {
  const { text } = useI18n();
  const subject = type === "findings"
    ? text("findings", "지적사항")
    : text("internal comparison", "내부 비교");
  return (
    <div className="artifact-language-controls" aria-label={text("Result language", "결과 언어")}>
      {(["en", "ko"] as const).map((language) => {
        const available = availableLanguages.has(language);
        const pending = pendingLanguages.has(language);
        const label = language === "ko" ? "한국어" : "English";
        if (!available) {
          return (
            <button
              type="button"
              className="artifact-language-controls__generate"
              disabled={pending}
              onClick={() => onGenerate(language)}
              key={language}
            >
              {pending ? <LoaderCircle className="spin" size={14} /> : <Sparkles size={14} />}
              {pending
                ? text(`Generating ${label}…`, `${label} 생성 중…`)
                : text(`Add ${label} ${subject}`, `${label} ${subject} 생성`)}
            </button>
          );
        }
        return (
          <button
            type="button"
            className={currentLanguage === language ? "artifact-language-controls__active" : ""}
            aria-pressed={currentLanguage === language}
            onClick={() => onSelect(language)}
            key={language}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

function GenerationStatus({ pending }: { pending: Set<GenerationKey> }) {
  const { text } = useI18n();
  if (!pending.size) return null;
  const label = (key: GenerationKey) => {
    if (key === "translation") return text("Korean full-letter translation", "전체 원문 한국어 번역");
    const [type, language] = key.split(":") as [AnalysisArtifactType, LetterAiArtifactLanguage];
    const artifactLabel = type === "findings"
      ? text("findings", "지적사항")
      : text("internal comparison", "내부 비교");
    return `${language === "ko" ? "한국어" : "English"} ${artifactLabel}`;
  };
  return (
    <section className="artifact-generation-status" aria-live="polite">
      <div>
        <LoaderCircle className="spin" size={17} aria-hidden="true" />
        <span>
          <strong>{text(
            `${pending.size} generation ${pending.size === 1 ? "job" : "jobs"} running`,
            `생성 작업 ${pending.size}건 진행 중`,
          )}</strong>
          {text("You can keep reading or start another result.", "계속 읽거나 다른 결과 생성을 시작할 수 있습니다.")}
        </span>
      </div>
      <ul>{Array.from(pending).map((key) => <li key={key}><CircleDot size={12} /> {label(key)}</li>)}</ul>
    </section>
  );
}

function FindingResult({ finding, onAnchor }: { finding: AiLetterFinding; onAnchor: (anchor: string) => void }) {
  const { text } = useI18n();
  const attention = {
    high: text("High attention", "높은 주의"),
    medium: text("Medium attention", "중간 주의"),
    routine: text("Routine attention", "일반 주의"),
  }[finding.attentionLevel];

  return (
    <article className={`ai-finding ai-finding--${finding.attentionLevel}`}>
      <header className="ai-finding__header">
        <div className="ai-finding__marker">
          <span className="ai-finding__number">{finding.label}</span>
          <span className={`ai-attention-label ai-attention-label--${finding.attentionLevel}`}>{attention}</span>
        </div>
        <div className="ai-finding__title">
          <h3>{finding.title}</h3>
          {finding.categories.length ? (
            <div className="tag-list">
              {finding.categories.map((category) => <span key={category}>{category}</span>)}
            </div>
          ) : null}
        </div>
      </header>
      <div className={`ai-finding__body${finding.requestedActions.length ? "" : " ai-finding__body--single"}`}>
        <section className="ai-finding__narrative">
          <h4>{text("Finding narrative", "지적 내용")}</h4>
          <p className="ai-finding__statement">{finding.finding}</p>
        </section>
        {finding.requestedActions.length ? (
          <section className="ai-finding__actions">
            <h4>{text("FDA-requested actions", "FDA 요청 조치")}</h4>
            <ul>{finding.requestedActions.map((action) => <li key={action}>{action}</li>)}</ul>
          </section>
        ) : null}
      </div>
      {finding.evidenceAnchors.length ? (
        <footer className="ai-anchor-list ai-finding__evidence">
          <span>{text("Source evidence", "원문 근거")}</span>
          {finding.evidenceAnchors.map((anchor) => (
            <button type="button" key={anchor} onClick={() => onAnchor(anchor)}>
              <Link2 size={13} aria-hidden="true" /> {anchor}
            </button>
          ))}
        </footer>
      ) : null}
    </article>
  );
}

function SectionIndex({
  sections,
  translated,
  sourceUrl,
}: {
  sections: Array<OriginalSection | TranslatedLetterSection>;
  translated: boolean;
  sourceUrl: string;
}) {
  const { text } = useI18n();
  return (
    <aside className="original-index">
      <p className="micro-label">{translated ? text("Korean section index", "한국어 번역 색인") : text("Official source index", "공식 원문 색인")}</p>
      {sections.length ? sections.map((section, index) => (
        <a href={`#${section.anchor}`} key={section.anchor} lang={translated ? "ko" : "en"}>
          <span>{String(index + 1).padStart(2, "0")}</span>{section.heading}
        </a>
      )) : <p>{text("No normalized section index is available.", "정규화된 원문 색인이 없습니다.")}</p>}
      <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
        <ExternalLink size={13} /> {text("Canonical FDA page", "FDA 정식 페이지")}
      </a>
    </aside>
  );
}

export function LetterDetail({ letter, initiallySaved }: { letter: Letter; initiallySaved: boolean }) {
  const { locale, text } = useI18n();
  const router = useRouter();
  const [tab, setTab] = useState<ContentTab>("Original");
  const [copied, setCopied] = useState(false);
  const [artifacts, setArtifacts] = useState(letter.aiArtifacts);
  const pendingRef = useRef(new Set<GenerationKey>());
  const [pendingGenerations, setPendingGenerations] = useState(new Set<GenerationKey>());
  const [artifactErrors, setArtifactErrors] = useState<Partial<Record<GenerationKey, string>>>({});
  const [showTranslation, setShowTranslation] = useState(false);

  const artifactByType = useMemo(
    () => new Map(artifacts.map((artifact) => [artifactKey(artifact.artifactType, artifact.language), artifact])),
    [artifacts],
  );
  const translation = artifactByType.get(artifactKey("translation", "ko"));
  const initialArtifactLanguage = (type: AnalysisArtifactType): LetterAiArtifactLanguage => {
    const preferred = locale === "ko" ? "ko" : "en";
    if (artifactByType.has(artifactKey(type, preferred))) return preferred;
    return artifactByType.has(artifactKey(type, "en")) ? "en" : "ko";
  };
  const [findingsLanguage, setFindingsLanguage] = useState<LetterAiArtifactLanguage>(
    () => initialArtifactLanguage("findings"),
  );
  const [summaryLanguage, setSummaryLanguage] = useState<LetterAiArtifactLanguage>(
    () => initialArtifactLanguage("summary"),
  );
  const findings = artifactByType.get(artifactKey("findings", findingsLanguage));
  const summary = artifactByType.get(artifactKey("summary", summaryLanguage));
  const availableFindingsLanguages = new Set(
    (["en", "ko"] as const).filter((language) => artifactByType.has(artifactKey("findings", language))),
  );
  const availableSummaryLanguages = new Set(
    (["en", "ko"] as const).filter((language) => artifactByType.has(artifactKey("summary", language))),
  );
  const pendingFindingsLanguages = new Set(
    (["en", "ko"] as const).filter((language) => pendingGenerations.has(`findings:${language}`)),
  );
  const pendingSummaryLanguages = new Set(
    (["en", "ko"] as const).filter((language) => pendingGenerations.has(`summary:${language}`)),
  );
  const translatedSections = translation?.content.sections ?? [];
  const sourceSections = showTranslation && translatedSections.length ? translatedSections : letter.originalSections;

  const openAnchor = (anchor: string) => {
    setShowTranslation(false);
    setTab("Original");
    window.setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  };

  const copyReference = async () => {
    await navigator.clipboard?.writeText(`${letter.company} — FDA Warning Letter ${letter.marcsCms} (${formatDate(letter.issueDate, undefined, "en")})`);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const generateArtifact = async (
    artifactType: LetterAiArtifactType,
    language: LetterAiArtifactLanguage,
  ) => {
    const key = generationKey(artifactType, language);
    if (pendingRef.current.has(key)) return;
    pendingRef.current.add(key);
    setPendingGenerations(new Set(pendingRef.current));
    setArtifactErrors((current) => ({ ...current, [key]: undefined }));
    try {
      const response = await fetch(
        `/api/drug-letters/${encodeURIComponent(letter.id)}/ai-artifacts/${artifactType}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ language }),
        },
      );
      const payload = await response.json() as LetterAiArtifact & { error?: string; requestId?: string };
      if (!response.ok) {
        throw new ArtifactRequestError(payload.requestId);
      }
      const artifact = payload as LetterAiArtifact;
      setArtifacts((current) => [
        artifact,
        ...current.filter((item) => !(
          item.artifactType === artifact.artifactType && item.language === artifact.language
        )),
      ]);
      if (artifactType === "translation") setShowTranslation(true);
      if (artifactType === "findings") setFindingsLanguage(language);
      if (artifactType === "summary") setSummaryLanguage(language);
    } catch (error) {
      const requestDetail = error instanceof ArtifactRequestError && error.requestId
        ? ` ${text("Reference", "참조")}: ${error.requestId}`
        : "";
      setArtifactErrors((current) => ({
        ...current,
        [key]: `${text(
          "The validated result could not be generated. Retry shortly; no unvalidated result was saved.",
          "검증된 결과를 생성하지 못했습니다. 잠시 후 다시 시도해 주세요. 검증되지 않은 결과는 저장되지 않았습니다.",
        )}${requestDetail}`,
      }));
    } finally {
      pendingRef.current.delete(key);
      setPendingGenerations(new Set(pendingRef.current));
    }
  };

  const openLetterChat = () => {
    router.push(`/dashboard?letter=${encodeURIComponent(letter.id)}&company=${encodeURIComponent(letter.company)}`);
  };

  const activateTab = (nextTab: ContentTab, moveFocus = false) => {
    setTab(nextTab);
    if (moveFocus) {
      window.requestAnimationFrame(() => document.getElementById(`letter-tab-${nextTab.toLowerCase()}`)?.focus());
    }
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | undefined;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % contentTabs.length;
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (index - 1 + contentTabs.length) % contentTabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = contentTabs.length - 1;
    if (nextIndex === undefined) return;
    event.preventDefault();
    activateTab(contentTabs[nextIndex], true);
  };

  const findingItems = findings?.content.findings ?? [];
  const highAttentionFindingCount = findingItems.filter((finding) => finding.attentionLevel === "high").length;
  const requestedActionCount = findingItems.reduce((total, finding) => total + finding.requestedActions.length, 0);
  const evidenceAnchorCount = new Set(findingItems.flatMap((finding) => finding.evidenceAnchors)).size;

  const translationButton: ReactNode = translatedSections.length ? (
    <button className="button button--secondary" type="button" onClick={() => setShowTranslation((current) => !current)}>
      <Languages size={17} aria-hidden="true" />
      {showTranslation ? text("View English original", "영문 원문 보기") : text("View saved Korean translation", "저장된 한국어 번역 보기")}
    </button>
  ) : (
    <button
      className="button button--secondary"
      type="button"
      disabled={pendingGenerations.has("translation")}
      onClick={() => generateArtifact("translation", "ko")}
      aria-busy={pendingGenerations.has("translation")}
    >
      {pendingGenerations.has("translation") ? <LoaderCircle className="spin" size={17} /> : <Languages size={17} />}
      {pendingGenerations.has("translation") ? text("Translating…", "전체 번역 중…") : text("Translate full letter to Korean", "전체 원문 한국어 번역")}
    </button>
  );

  return (
    <article className="page-stack detail-page detail-page--focused">
      <div className="detail-page__utility-row">
        <nav className="detail-breadcrumb dossier-reveal" aria-label={text("Breadcrumb", "이동 경로")}>
          <Link href="/drug-letters"><ArrowLeft size={15} aria-hidden="true" /> {text("Drug Letters", "의약품 경고서한")}</Link>
          <span>/</span>
          <span>{letter.marcsCms}</span>
        </nav>
        <PageGuide
          className="detail-page__guide"
          includePageHeading={false}
          title={{ ko: "경고서한 상세", en: "Warning Letter Detail" }}
          context={{ ko: "FDA 공식 영문 원문과 저장형 AI 분석", en: "Official FDA source with saved AI analysis" }}
          description={{
            ko: "원문을 확인하고, 전체 한국어 번역과 영어·한국어 지적사항 및 내부 비교 브리프를 현재 원문 버전에 저장하세요. 여러 작업을 동시에 실행할 수 있습니다.",
            en: "Read the source, then generate a Korean full-letter translation plus English or Korean findings and internal comparison briefs. Multiple jobs can run together for the current source version.",
          }}
        />
      </div>

      <header className="record-summary-card dossier-reveal">
        <div className="record-summary-card__identity">
          <div className="record-summary-card__topline">
            <p className="record-kicker">{text("FDA official English record", "FDA 공식 영문 기록")}</p>
            {!["pending", "not_generated"].includes(letter.reviewState)
              ? <StatusPill state={letter.reviewState} />
              : null}
          </div>
          <h1 lang="en">{letter.company}</h1>
          <p className="record-subject" lang="en">{letter.subject}</p>
        </div>
        <div className="record-summary-card__actions">
          <LetterBookmarkButton letterId={letter.id} initiallySaved={initiallySaved} />
          <a className="button button--fda" href={letter.sourceUrl} target="_blank" rel="noopener noreferrer">
            <Image src="/brand/fda-logo-icon.svg" alt="" aria-hidden="true" width={18} height={22} />
            {text("Open FDA source", "FDA 원문 열기")}
            <ExternalLink size={15} aria-hidden="true" />
          </a>
          <button className="button button--secondary" type="button" onClick={copyReference}>
            {copied ? <CheckCircle2 size={16} /> : <Copy size={16} />}
            {copied ? text("Copied", "복사됨") : text("Copy reference", "참조 복사")}
          </button>
        </div>
        <dl className="record-facts">
          <div><dt>{text("Issued", "발행일")}</dt><dd>{formatDate(letter.issueDate, undefined, locale)}</dd></div>
          <div><dt>{text("Posted", "게시일")}</dt><dd>{formatDate(letter.postedDate, undefined, locale)}</dd></div>
          <div className="record-fact--office"><dt>{text("Issuing office", "발행 부서")}</dt><dd lang="en">{letter.issuingOffice}</dd></div>
          <div><dt>{text("Recipient country", "수신자 국가")}</dt><dd lang="en">{letter.country}</dd></div>
        </dl>
      </header>

      <nav className="record-tabs dossier-reveal dossier-reveal--delay-1" aria-label={text("Letter sections", "경고서한 섹션")}>
        <div className="record-tab-list" role="tablist">
          {contentTabs.map((item, index) => (
            <button
              key={item}
              type="button"
              role="tab"
              id={`letter-tab-${item.toLowerCase()}`}
              aria-controls={`letter-panel-${item.toLowerCase()}`}
              aria-selected={tab === item}
              tabIndex={tab === item ? 0 : -1}
              className={tab === item ? "record-tab--active" : ""}
              onClick={() => activateTab(item)}
              onKeyDown={(event) => handleTabKeyDown(event, index)}
            >
              <span className="record-tab__index">0{index + 1}</span>
              {text(tabLabels[item].en, tabLabels[item].ko)}
              {item === "Findings" && Array.from(pendingGenerations).some((key) => key.startsWith("findings:"))
                ? <LoaderCircle className="spin record-tab__spinner" size={13} aria-label={text("Generating", "생성 중")} />
                : null}
              {item === "Summary" && Array.from(pendingGenerations).some((key) => key.startsWith("summary:"))
                ? <LoaderCircle className="spin record-tab__spinner" size={13} aria-label={text("Generating", "생성 중")} />
                : null}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="record-tab-link"
          onClick={openLetterChat}
        >
          <span className="record-tab__index">04</span>
          {text("Ask", "질문")}
          <ArrowUpRight size={15} aria-hidden="true" />
        </button>
      </nav>

      <GenerationStatus pending={pendingGenerations} />

      <div
        className="record-tab-content dossier-reveal dossier-reveal--delay-2"
        role="tabpanel"
        id={`letter-panel-${tab.toLowerCase()}`}
        aria-labelledby={`letter-tab-${tab.toLowerCase()}`}
        tabIndex={0}
      >
        {tab === "Original" ? (
          <div className="original-workspace">
            <SectionIndex sections={sourceSections} translated={showTranslation} sourceUrl={letter.sourceUrl} />
            <section className="source-document">
              <header>
                <div>
                  <p className="eyebrow">{showTranslation ? text("Saved Korean translation", "저장된 한국어 번역") : text("Official FDA English source", "FDA 공식 영문 원문")}</p>
                  <h2 lang="en">{letter.company}</h2>
                </div>
                <div className="source-document__tools">{translationButton}</div>
              </header>
              {artifactErrors.translation ? <p className="ai-artifact-error" role="alert"><AlertTriangle size={15} /> {artifactErrors.translation}</p> : null}
              {showTranslation && translation ? <ArtifactNotice artifact={translation} /> : null}
              {showTranslation && translation ? (
                <p className="translation-safety-note">
                  <AlertTriangle size={15} aria-hidden="true" />
                  {text(
                    "AI translation is provided for reading support. Confirm regulatory decisions against the official FDA English source.",
                    "AI 번역은 열람 지원용입니다. 규제 판단에 사용하는 내용은 FDA 공식 영문 원문과 반드시 대조하세요.",
                  )}
                </p>
              ) : null}
              {sourceSections.length ? sourceSections.map((section) => (
                <section id={section.anchor} className="source-section" key={section.anchor}>
                  <div className="source-anchor"><Link2 size={13} /> {section.anchor}</div>
                  <h3 lang={showTranslation ? "ko" : "en"}>{section.heading}</h3>
                  {section.paragraphs.map((paragraph, index) => (
                    <RichParagraph key={`${section.anchor}-${index}`} lang={showTranslation ? "ko" : "en"}>{paragraph}</RichParagraph>
                  ))}
                </section>
              )) : (
                <div className="source-unavailable">
                  <FileSearch size={24} />
                  <h3>{text("Normalized source pending", "정규화된 원문 준비 중")}</h3>
                  <p>{text("Use the FDA source button for the authoritative document.", "공식 문서는 FDA 원문 버튼에서 확인하세요.")}</p>
                </div>
              )}
            </section>
          </div>
        ) : null}

        {tab === "Findings" ? (
          <section className="ai-result-page">
            {findings?.content.findings?.length ? (
              <>
                <header className="ai-result-heading">
                  <div>
                    <p className="eyebrow">{text("Validated AI analysis", "검증된 AI 분석")}</p>
                    <h2>{text("Clean findings from the full letter", "경고서한 전체에서 추출한 핵심 지적사항")}</h2>
                    <p className="ai-result-heading__description">{text(
                      "A structured register of the FDA's observations, requested actions, and linked source evidence.",
                      "FDA의 지적 내용, 요청 조치, 연결된 원문 근거를 구조화한 분석 기록입니다.",
                    )}</p>
                  </div>
                  <div className="ai-result-heading__tools">
                    <ArtifactLanguageControls
                      type="findings"
                      currentLanguage={findingsLanguage}
                      availableLanguages={availableFindingsLanguages}
                      pendingLanguages={pendingFindingsLanguages}
                      onSelect={setFindingsLanguage}
                      onGenerate={(language) => generateArtifact("findings", language)}
                    />
                    <ArtifactNotice artifact={findings} />
                  </div>
                </header>
                <section className="analysis-overview analysis-overview--findings" aria-label={text("Findings overview", "지적사항 개요")}>
                  <div className="analysis-overview__intro">
                    <span><FileSearch size={20} aria-hidden="true" /></span>
                    <div>
                      <small>{text("Analysis register", "분석 기록")}</small>
                      <strong>{text("Current FDA source version", "현재 FDA 원문 버전")}</strong>
                    </div>
                  </div>
                  <dl>
                    <div><dt>{text("Findings", "지적사항")}</dt><dd>{findingItems.length}</dd></div>
                    <div><dt>{text("High attention", "높은 주의")}</dt><dd>{highAttentionFindingCount}</dd></div>
                    <div><dt>{text("Requested actions", "요청 조치")}</dt><dd>{requestedActionCount}</dd></div>
                    <div><dt>{text("Evidence links", "원문 근거")}</dt><dd>{evidenceAnchorCount}</dd></div>
                  </dl>
                </section>
                <div className="ai-findings-list" lang={findings.language}>
                  {findings.content.findings.map((finding, index) => (
                    <FindingResult finding={{ ...finding, label: finding.label || String(index + 1).padStart(2, "0") }} onAnchor={openAnchor} key={`${finding.title}-${index}`} />
                  ))}
                </div>
              </>
            ) : (
              <GeneratePanel
                type="findings"
                pendingLanguages={pendingFindingsLanguages}
                errors={{
                  en: artifactErrors["findings:en"],
                  ko: artifactErrors["findings:ko"],
                }}
                onGenerate={(language) => generateArtifact("findings", language)}
              />
            )}
          </section>
        ) : null}

        {tab === "Summary" ? (
          <section className="ai-result-page">
            {summary?.content.executiveSummary ? (
              <>
                <header className="ai-result-heading">
                  <div>
                    <p className="eyebrow">{text("Validated practical brief", "검증된 실무 브리프")}</p>
                    <h2>{text("Internal comparison brief", "내부 비교 브리프")}</h2>
                    <p className="ai-result-heading__description">{text(
                      "An executive reading of the letter with source-linked attention points and neutral prompts for internal review.",
                      "경고서한의 핵심 내용과 원문 연계 주의사항, 중립적인 내부 검토 질문을 한 흐름으로 정리했습니다.",
                    )}</p>
                  </div>
                  <div className="ai-result-heading__tools">
                    <ArtifactLanguageControls
                      type="summary"
                      currentLanguage={summaryLanguage}
                      availableLanguages={availableSummaryLanguages}
                      pendingLanguages={pendingSummaryLanguages}
                      onSelect={setSummaryLanguage}
                      onGenerate={(language) => generateArtifact("summary", language)}
                    />
                    <ArtifactNotice artifact={summary} />
                  </div>
                </header>
                <article className="ai-summary-sheet" lang={summary.language}>
                  <section className="ai-summary-hero">
                    <div className="ai-summary-hero__label">
                      <span><Sparkles size={17} aria-hidden="true" /></span>
                      <small>{text("Brief overview", "브리프 개요")}</small>
                    </div>
                    <p className="ai-summary-lead">{summary.content.executiveSummary}</p>
                  </section>
                  <div className="ai-summary-layout">
                    {summary.content.attentionPoints?.length ? (
                      <section className="attention-grid">
                        <header className="analysis-section-heading">
                          <span>01</span>
                          <div>
                            <h3>{text("Attention points", "주의 깊게 볼 사항")}</h3>
                            <p>{text(
                              `${summary.content.attentionPoints.length} source-linked points for practical review`,
                              `실무 검토를 위한 원문 연계 포인트 ${summary.content.attentionPoints.length}건`,
                            )}</p>
                          </div>
                        </header>
                        <div>
                          {summary.content.attentionPoints.map((point, index) => (
                            <article key={`${point.title}-${index}`}>
                              <header>
                                <span>{String(index + 1).padStart(2, "0")}</span>
                                <h4>{point.title}</h4>
                              </header>
                              <p>{point.rationale}</p>
                              {point.sourceAnchors.length ? <div className="ai-anchor-list">{point.sourceAnchors.map((anchor) => <button type="button" key={anchor} onClick={() => openAnchor(anchor)}><Link2 size={13} /> {anchor}</button>)}</div> : null}
                            </article>
                          ))}
                        </div>
                      </section>
                    ) : null}
                    {summary.content.comparisonQuestions?.length ? (
                      <section className="comparison-checklist">
                        <header className="analysis-section-heading">
                          <span>02</span>
                          <div>
                            <h3>{text("Internal comparison questions", "내부 비교 질문")}</h3>
                            <p>{text(
                              "Neutral prompts for reviewing your own systems and workflows.",
                              "자체 시스템과 업무 절차를 검토하기 위한 중립적인 질문입니다.",
                            )}</p>
                          </div>
                        </header>
                        <ol>{summary.content.comparisonQuestions.map((question) => <li key={question}>{question}</li>)}</ol>
                      </section>
                    ) : null}
                  </div>
                  <div className="summary-guardrail">
                    <ShieldCheck size={20} aria-hidden="true" />
                    <p><strong>{text("Interpretation boundary.", "해석 범위.")}</strong> {summary.content.disclaimer || text("The official FDA source remains authoritative. This AI-derived brief does not determine Daewoong's compliance status.", "FDA 공식 원문이 최종 기준입니다. 이 AI 파생 브리프는 대웅의 컴플라이언스 상태를 판단하지 않습니다.")}</p>
                  </div>
                </article>
              </>
            ) : (
              <GeneratePanel
                type="summary"
                pendingLanguages={pendingSummaryLanguages}
                errors={{
                  en: artifactErrors["summary:en"],
                  ko: artifactErrors["summary:ko"],
                }}
                onGenerate={(language) => generateArtifact("summary", language)}
              />
            )}
          </section>
        ) : null}
      </div>

      <footer className="record-integrity">
        <ShieldCheck size={17} aria-hidden="true" />
        <span>{text("Official source retained · bilingual AI results version-bound and reusable · parallel generation supported", "공식 원문 보존 · 이중 언어 AI 결과의 버전 연계 및 재사용 · 병렬 생성 지원")}</span>
        <code>MARCS-CMS {letter.marcsCms}</code>
      </footer>
    </article>
  );
}
