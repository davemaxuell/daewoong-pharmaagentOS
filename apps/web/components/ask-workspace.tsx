"use client";

import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  BookmarkPlus,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Copy,
  ExternalLink,
  Filter,
  LockKeyhole,
  MessageSquareQuote,
  Quote,
  Search,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { askDrugCorpus } from "@/app/(portal)/ask/actions";
import { useI18n } from "@/lib/i18n";
import type { DataMode, Letter, RagAnswer, RagFilter } from "@/lib/types";
import { formatDate, ModeBadge } from "@/components/ui";

const prompts = [
  {
    en: "What process-validation controls recur in API warning letters?",
    ko: "API 경고서에서 반복적으로 나타나는 공정 밸리데이션 관리 항목은 무엇인가요?",
  },
  {
    en: "Summarize Quality Unit concerns tied to 21 CFR 211.22.",
    ko: "21 CFR 211.22와 관련된 품질 부서 우려 사항을 요약해 주세요.",
  },
  {
    en: "Which source evidence discusses stability or retest support?",
    ko: "안정성 또는 재시험 근거를 다루는 원문 증거는 무엇인가요?",
  },
];

export function AskWorkspace({
  letters,
  mode,
  initialLetterId,
  initialCompany,
}: {
  letters: Letter[];
  mode: DataMode;
  initialLetterId: string;
  initialCompany: string;
}) {
  const { locale, text } = useI18n();
  const initialLetter = letters.find((letter) => letter.id === initialLetterId);
  const [question, setQuestion] = useState(
    initialLetter
      ? text(
          `What are the principal FDA findings and requested actions for ${initialLetter.company}?`,
          `${initialLetter.company}에 대한 FDA의 주요 지적 사항과 요청 조치는 무엇인가요?`,
        )
      : "",
  );
  const [filters, setFilters] = useState<RagFilter>(initialLetterId ? { letterId: initialLetterId, company: initialCompany || initialLetter?.company } : {});
  const [answer, setAnswer] = useState<RagAnswer>();
  const [activeCitation, setActiveCitation] = useState(0);
  const [error, setError] = useState<"question_too_short" | "query_failed">();
  const [saved, setSaved] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down">();
  const [copied, setCopied] = useState(false);
  const [pending, startTransition] = useTransition();
  const questionTouched = useRef(false);

  useEffect(() => {
    if (!initialLetter || questionTouched.current) return;
    setQuestion(text(
      `What are the principal FDA findings and requested actions for ${initialLetter.company}?`,
      `${initialLetter.company}에 대한 FDA의 주요 지적 사항과 요청 조치는 무엇인가요?`,
    ));
  }, [initialLetter, text]);

  const categories = useMemo(() => [...new Set(letters.flatMap((letter) => letter.categories))].sort(), [letters]);
  const subtypes = useMemo(() => [...new Set(letters.flatMap((letter) => letter.drugSubtypes))].sort(), [letters]);
  const regulations = useMemo(() => [...new Set(letters.flatMap((letter) => letter.regulations))].sort(), [letters]);

  const submit = () => {
    setError(undefined);
    setSaved(false);
    setFeedback(undefined);
    startTransition(async () => {
      try {
        const result = await askDrugCorpus(question, filters, "auto");
        setAnswer(result.data);
        setActiveCitation(0);
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : "";
        setError(message === "Enter a specific question of at least 8 characters." ? "question_too_short" : "query_failed");
      }
    });
  };

  const setFilter = (key: keyof RagFilter, value: string) => setFilters((current) => ({ ...current, [key]: value || undefined }));
  const citation = answer?.citations[activeCitation];
  const previewAnswer = answer?.answer === "Across the indexed Drug warning-letter evidence, FDA’s recurring process-validation concerns cluster around three controls: demonstrating reproducibility before commercial distribution, retaining complete master and batch instructions, and maintaining continued verification with stability or process-trend evidence. The cited letter below directly supports those source facts. It does not establish a Daewoong gap or change a regulatory requirement."
    ? "색인된 의약품 경고서 증거 전반에서 FDA가 반복적으로 제기한 공정 밸리데이션 우려는 세 가지 관리 항목으로 모입니다. 상업적 유통 전 재현성 입증, 완전한 마스터 및 배치 지침 보존, 안정성 또는 공정 추세 증거를 통한 지속적 검증 유지입니다. 아래 인용 경고서는 이러한 원문 사실을 직접 뒷받침합니다. 이는 대웅의 격차를 입증하거나 규제 요건을 변경하지 않습니다."
    : answer?.answer;
  const localizedAnswer = answer ? text(answer.answer, previewAnswer ?? answer.answer) : "";
  const answerLanguage = /[가-힣]/.test(localizedAnswer) ? "ko" : "en";
  const documentTypeLabel = (value: string) => {
    if (value === "Warning letter") return text("Warning letter", "경고서");
    if (value === "Response" || value === "Response letter") return text(value, "회신서");
    if (value === "Closeout" || value === "Closeout letter") return text(value, "종결서");
    return value;
  };

  return (
    <div className="page-stack ask-page">
      <header className="ask-hero dossier-reveal">
        <div>
          <p className="eyebrow">{text("Controlled retrieval workspace", "통제된 검색 작업공간")}</p>
          <h1>{text("Ask the Drug corpus.", "의약품 코퍼스에 질문하세요.")}</h1>
          <p>{text(
            "Answers are synthesized only from authorized, admitted FDA evidence. Unsupported conclusions are refused.",
            "답변은 승인되어 수록된 FDA 증거만을 바탕으로 생성되며, 근거 없는 결론은 제공하지 않습니다.",
          )}</p>
        </div>
        <div className="ask-hero__assurance"><LockKeyhole size={18} /><div><span>{text("Retrieval boundary", "검색 범위")}</span><strong>FDA Product = Drugs</strong><small>{text("Authorization applied before search", "검색 전에 권한을 적용합니다")}</small></div></div>
        <ModeBadge mode={mode} />
      </header>

      <section className="ask-composer dossier-reveal dossier-reveal--delay-1">
        <div className="ask-composer__input">
          <MessageSquareQuote size={22} aria-hidden="true" />
          <label>
            <span className="sr-only">{text("Question", "질문")}</span>
            <textarea
              value={question}
              maxLength={2000}
              onChange={(event) => { questionTouched.current = true; setQuestion(event.target.value); }}
              onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") submit(); }}
              placeholder={text(
                "Ask about recurring FDA findings, requested actions, exact citations, or evidence patterns…",
                "반복되는 FDA 지적 사항, 요청 조치, 정확한 인용 또는 증거 패턴을 질문하세요…",
              )}
            />
          </label>
          <button className="ask-submit" type="button" onClick={submit} disabled={pending || question.trim().length < 8}>
            {pending ? <span className="button-spinner" /> : <ArrowRight size={18} />}
            {pending ? text("Retrieving evidence", "증거 검색 중") : text("Search evidence", "증거 검색")}
          </button>
        </div>
        <div className="ask-composer__footer">
          <span><ShieldCheck size={14} /> {text("Evidence-first · no general web or model memory", "증거 우선 · 일반 웹 또는 모델 메모리 미사용")}</span>
          <small>{question.length}/2,000 · {text("⌘ Enter to run", "⌘ Enter로 실행")}</small>
        </div>
      </section>

      <section className="rag-filters dossier-reveal dossier-reveal--delay-1" aria-label={text("Retrieval filters", "검색 필터")}>
        <span className="rag-filters__label"><Filter size={15} /> {text("Narrow authorized evidence", "승인된 증거 범위 좁히기")}</span>
        <label><span>{text("From", "시작일")}</span><input type="date" value={filters.dateFrom ?? ""} onChange={(event) => setFilter("dateFrom", event.target.value)} /></label>
        <label><span>{text("To", "종료일")}</span><input type="date" value={filters.dateTo ?? ""} onChange={(event) => setFilter("dateTo", event.target.value)} /></label>
        <label><span>{text("Category", "범주")}</span><div><select value={filters.category ?? ""} onChange={(event) => setFilter("category", event.target.value)}><option value="">{text("Any category", "모든 범주")}</option>{categories.map((value) => <option key={value}>{value}</option>)}</select><ChevronDown size={13} /></div></label>
        <label><span>{text("Authority", "규제 근거")}</span><div><select value={filters.regulation ?? ""} onChange={(event) => setFilter("regulation", event.target.value)}><option value="">{text("Any exact citation", "모든 정확한 인용")}</option>{regulations.map((value) => <option key={value}>{value}</option>)}</select><ChevronDown size={13} /></div></label>
        <label><span>{text("Drug subtype", "의약품 세부 유형")}</span><div><select value={filters.subtype ?? ""} onChange={(event) => setFilter("subtype", event.target.value)}><option value="">{text("Any subtype", "모든 세부 유형")}</option>{subtypes.map((value) => <option key={value}>{value}</option>)}</select><ChevronDown size={13} /></div></label>
        {filters.letterId ? <button className="constrained-filter" type="button" aria-label={text("Remove single-letter filter", "단일 경고서 필터 제거")} aria-pressed="true" onClick={() => setFilters((current) => ({ ...current, letterId: undefined, company: undefined }))}><LockKeyhole size={13} /> {filters.company ?? text("Single letter", "단일 경고서")} <span>×</span></button> : null}
      </section>

      {error ? <div className="inline-error" role="alert"><CircleAlert size={17} /><p><strong>{text("Query not completed.", "질의를 완료하지 못했습니다.")}</strong> {error === "question_too_short" ? text("Enter a specific question of at least 8 characters.", "8자 이상의 구체적인 질문을 입력해 주세요.") : text("The evidence workspace could not complete this query.", "증거 작업공간에서 이 질의를 완료하지 못했습니다.")}</p></div> : null}

      {!answer && !pending ? (
        <section className="ask-empty dossier-reveal dossier-reveal--delay-2">
          <div className="ask-empty__graphic"><span>FDA</span><i /><Search size={25} /><i /><span>{text("Evidence", "증거")}</span></div>
          <div><p className="eyebrow">{text("A bounded answer begins with a precise question", "범위가 명확한 답변은 정확한 질문에서 시작됩니다")}</p><h2>{text("Try an evidence-led prompt.", "증거 중심 질문을 사용해 보세요.")}</h2></div>
          <div className="prompt-list">{prompts.map((prompt) => {
            const label = text(prompt.en, prompt.ko);
            return <button type="button" key={prompt.en} onClick={() => { questionTouched.current = true; setQuestion(label); }}><Sparkles size={14} /> {label}<ArrowRight size={14} /></button>;
          })}</div>
          <p><LockKeyhole size={14} /> {text(
            "Questions are internal-confidential. Full prompt text is excluded from general infrastructure logs.",
            "질문은 사내 기밀입니다. 전체 프롬프트 내용은 일반 인프라 로그에서 제외됩니다.",
          )}</p>
        </section>
      ) : null}

      {pending ? (
        <section className="rag-loading" role="status"><div className="rag-loading__beam" /><p>{text(
          "Authorizing corpus → retrieving official source chunks → validating citations",
          "코퍼스 권한 확인 → 공식 원문 청크 검색 → 인용 검증",
        )}</p></section>
      ) : null}

      {answer && !pending ? (
        <section className="rag-result dossier-reveal">
          <article className="answer-sheet">
            <header>
              <div><span className="answer-label"><Sparkles size={14} /> {answerLanguage === "ko" ? text("AI synthesis · Korean", "AI 종합 · 한국어") : text("AI synthesis · English", "AI 종합 · 영어")}</span><h2>{text("Answer", "답변")}</h2></div>
              <div className={`sufficiency sufficiency--${answer.evidenceSufficiency}`}><CheckCircle2 size={15} /> {text("Evidence", "증거")} {answer.evidenceSufficiency === "sufficient" ? text("sufficient", "충분") : answer.evidenceSufficiency === "partial" ? text("partial", "일부") : text("insufficient", "불충분")}</div>
            </header>
            <p className="answer-copy" lang={answerLanguage}>{localizedAnswer}</p>
            {Object.values(answer.filtersApplied).some(Boolean) ? <div className="applied-filters"><span>{text("Filters applied", "적용된 필터")}</span>{Object.entries(answer.filtersApplied).filter(([, value]) => value).map(([key, value]) => <code key={key}>{key === "dateFrom" ? text("from", "시작일") : key === "dateTo" ? text("to", "종료일") : key === "category" ? text("category", "범주") : key === "regulation" ? text("authority", "규제 근거") : key === "company" ? text("company", "회사") : key === "subtype" ? text("subtype", "세부 유형") : key === "letterId" ? text("letter", "경고서") : key}: {value}</code>)}</div> : null}
            <div className="answer-boundary"><CircleAlert size={17} /><p><strong>{text("Assistive interpretation.", "보조적 해석입니다.")}</strong> {text(
              "Verify consequential decisions against the cited FDA source. This answer does not assess Daewoong compliance or create a CAPA requirement.",
              "중요한 결정은 인용된 FDA 원문과 대조하여 확인하세요. 이 답변은 대웅의 규정 준수 여부를 평가하거나 CAPA 요건을 생성하지 않습니다.",
            )}</p></div>
            <footer>
              <div><button className={feedback === "up" ? "selected" : ""} type="button" aria-label={text("Helpful answer", "도움이 된 답변")} aria-pressed={feedback === "up"} onClick={() => setFeedback("up")}><ThumbsUp size={15} /></button><button className={feedback === "down" ? "selected" : ""} type="button" aria-label={text("Unhelpful answer", "도움이 되지 않은 답변")} aria-pressed={feedback === "down"} onClick={() => setFeedback("down")}><ThumbsDown size={15} /></button><span aria-live="polite">{feedback ? text("Feedback recorded", "피드백이 기록되었습니다") : text("Was this grounded?", "근거가 충분했나요?")}</span></div>
              <div><button type="button" onClick={async () => { await navigator.clipboard?.writeText(localizedAnswer); setCopied(true); }}><Copy size={14} /> <span aria-live="polite">{copied ? text("Copied", "복사됨") : text("Copy", "복사")}</span></button><button type="button" aria-pressed={saved} onClick={() => setSaved((value) => !value)}><BookmarkPlus size={14} /> {saved ? text("Saved", "저장됨") : text("Save question", "질문 저장")}</button></div>
            </footer>
            <small className="request-id">{text("Request", "요청")} {answer.requestId} · {formatDate(answer.generatedAt, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }, locale)}</small>
          </article>

          <aside className="evidence-rank">
            <header><div><p className="eyebrow">{text("Ranked evidence", "순위별 증거")}</p><h2>{text(`${answer.citations.length} official ${answer.citations.length === 1 ? "citation" : "citations"}`, `공식 인용 ${answer.citations.length}건`)}</h2></div><BookOpen size={19} /></header>
            <ol>{answer.citations.map((item, index) => <li key={item.id}><button className={activeCitation === index ? "active" : ""} type="button" aria-label={text(`Open citation ${index + 1} from ${item.company}`, `${item.company}의 ${index + 1}번 인용 열기`)} aria-current={activeCitation === index ? "true" : undefined} aria-pressed={activeCitation === index} onClick={() => setActiveCitation(index)}><span>{String(index + 1).padStart(2, "0")}</span><div><strong lang="en">{item.company}</strong><small>{documentTypeLabel(item.documentType)} · {formatDate(item.issueDate, undefined, locale)}</small><code>{Math.round(item.score * 100)}% {text("retrieval score", "검색 점수")}</code></div><ArrowRight size={14} /></button></li>)}</ol>
            {citation ? <div className="evidence-preview"><div><Quote size={15} /><span>{text("Source excerpt · English", "원문 발췌 · 영어")}</span></div><blockquote lang="en">{citation.excerpt}</blockquote><code>#{citation.anchor}</code><footer><Link href={`/drug-letters/${citation.letterId}`}>{text("Open evidence", "증거 열기")} <ArrowRight size={13} /></Link><a href={citation.sourceUrl} target="_blank" rel="noreferrer">{text("FDA source", "FDA 원문")} <ExternalLink size={13} /></a></footer></div> : <div className="evidence-preview evidence-preview--empty"><CircleAlert size={18} /><p>{text("No citation was returned. Treat this answer as insufficient evidence.", "인용이 반환되지 않았습니다. 이 답변을 불충분한 증거로 취급하세요.")}</p></div>}
          </aside>
        </section>
      ) : null}
    </div>
  );
}
