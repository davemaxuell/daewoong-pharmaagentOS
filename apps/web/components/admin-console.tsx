"use client";

import {
  Activity,
  AlertTriangle,
  ArchiveRestore,
  BellRing,
  CalendarRange,
  Check,
  CheckCircle2,
  CircleAlert,
  Database,
  ListRestart,
  LockKeyhole,
  Mail,
  PackageCheck,
  RefreshCcw,
  Save,
  ServerCog,
  Settings2,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, useTransition } from "react";
import { saveNotificationSettings, startCorpusSync, submitReprocess } from "@/app/(portal)/admin/actions";
import { PageGuide } from "@/components/page-guide";
import { useI18n } from "@/lib/i18n";
import type { AdminData, DataMode } from "@/lib/types";
import { formatDate, ModeBadge, SectionHeading } from "@/components/ui";

export function AdminConsole({ data, mode }: { data: AdminData; mode: DataMode }) {
  const { text } = useI18n();
  const [reprocessOpen, setReprocessOpen] = useState(false);
  const [letterId, setLetterId] = useState("");
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<{ letterId: string; jobId: string }>();
  const [error, setError] = useState<"letter_required" | "reason_required" | "request_failed">();
  const [notification, setNotification] = useState(data.notification);
  const [notificationEmail, setNotificationEmail] = useState(data.notification.targetEmail);
  const [notificationEnabled, setNotificationEnabled] = useState(data.notification.enabled);
  const [settingsNotice, setSettingsNotice] = useState(false);
  const [settingsError, setSettingsError] = useState(false);
  const [syncReceipt, setSyncReceipt] = useState<{ runId: string; status: string }>();
  const [syncError, setSyncError] = useState(false);
  const [pending, startTransition] = useTransition();
  const [settingsPending, startSettingsTransition] = useTransition();
  const [syncPending, startSyncTransition] = useTransition();
  const rootRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const scrimRef = useRef<HTMLDivElement>(null);
  const reprocessTriggerRef = useRef<HTMLButtonElement>(null);
  const deliveryReady = notification.smtpConfigured && notification.smtpDeliveryEnabled;
  const emailOperational = notificationEnabled && deliveryReady;
  const deliveryLabel = !notificationEnabled
    ? text("Paused", "일시 중지")
    : !notification.smtpConfigured
      ? text("Sender account required", "발신 계정 필요")
      : !notification.smtpDeliveryEnabled
        ? text("Delivery disabled", "발송 비활성화")
        : text("Sending enabled", "발송 가능");
  const hasOperationalAttention = data.health.some((check) => check.status !== "healthy") || data.exceptions.length > 0;
  const overallServiceLabel = mode !== "live"
    ? text("Preview data · backend status not asserted", "미리보기 데이터 · 백엔드 상태 확인 안 됨")
    : !data.health.length
      ? text("Connected · no processing run reported", "연결됨 · 보고된 처리 작업 없음")
      : hasOperationalAttention
        ? text("Connected · attention items reported", "연결됨 · 주의 항목 보고됨")
        : text("Connected · reported checks are healthy", "연결됨 · 보고된 점검 정상");
  const lastAssessed = data.health[0]?.checkedAt;

  useEffect(() => {
    if (!reprocessOpen) return;

    const dialog = dialogRef.current;
    const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previouslyFocused = activeElement && !dialog?.contains(activeElement) ? activeElement : reprocessTriggerRef.current;
    const root = rootRef.current;
    const background = root
      ? Array.from(root.children).filter((child): child is HTMLElement => child instanceof HTMLElement && child !== scrimRef.current)
      : [];
    const priorAttributes = background.map((element) => ({
      element,
      ariaHidden: element.getAttribute("aria-hidden"),
      hadInert: element.hasAttribute("inert"),
    }));

    background.forEach((element) => {
      element.setAttribute("inert", "");
      element.setAttribute("aria-hidden", "true");
    });

    const focusableElements = () => dialog
      ? Array.from(dialog.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'))
      : [];
    const focusFrame = window.requestAnimationFrame(() => {
      dialog?.querySelector<HTMLElement>("input:not([disabled])")?.focus();
    });
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setReprocessOpen(false);
        return;
      }
      if (event.key !== "Tab" || !dialog) return;

      const focusable = focusableElements();
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (document.activeElement === dialog) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (!dialog.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleKeyDown);
      priorAttributes.forEach(({ element, ariaHidden, hadInert }) => {
        if (!hadInert) element.removeAttribute("inert");
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      });
      previouslyFocused?.focus();
    };
  }, [reprocessOpen]);

  const adminValue = (value: string) => {
    const translations: Record<string, string> = {
      "FDA discovery": "FDA 발견",
      "Scope gate": "범위 게이트",
      "AI validation": "AI 검증",
      "Retrieval index": "검색 인덱스",
      "4,281 rows reconciled": "4,281개 행 조정 완료",
      "0 leakage indicators": "유출 지표 0건",
      "2 items routed to review": "2개 항목을 검토로 전달",
      "Source versions current": "원문 버전 최신 상태",
      "6 min ago": "6분 전",
      "12 min ago": "12분 전",
      "9 min ago": "9분 전",
      "4 min": "4분",
      "11 h": "11시간",
      "38 sec": "38초",
      "18 h": "18시간",
      "23 min": "23분",
      "Nominal": "정상",
      "Attention": "주의",
      "Review": "검토",
      "Disabled": "비활성화",
      "not configured": "구성되지 않음",
      "AMBIGUOUS": "모호함",
      "PARSE_FAILED": "구문 분석 실패",
      "Canonical Product metadata": "정식 제품 메타데이터",
      "Response PDF": "회신 PDF",
      "Product label present but value node was empty; downstream publication withheld.": "제품 라벨은 있으나 값 노드가 비어 있어 후속 게시를 보류했습니다.",
      "Text extraction confidence below threshold; OCR/manual review required.": "텍스트 추출 신뢰도가 기준치 미만이어서 OCR 또는 수동 검토가 필요합니다.",
      "Drug scope rule": "의약품 범위 규칙",
      "HTML parser": "HTML 파서",
      "Summary schema": "요약 스키마",
      "Taxonomy": "분류 체계",
      "Chunker": "청킹 처리기",
      "Grounded answer model": "근거 기반 답변 모델",
      "Retrieval embeddings": "검색 임베딩",
      "Application": "애플리케이션",
      "Current runtime": "현재 런타임",
      "Not reported": "보고되지 않음",
      "Not reported by service": "서비스에서 보고하지 않음",
      "No metrics reported": "보고된 지표 없음",
      "Running": "실행 중",
      "Pending": "대기 중",
      "succeeded": "성공",
      "partial": "일부 완료",
      "failed": "실패",
      "running": "실행 중",
      "pending": "대기 중",
      "Drug corpus admission configuration": "의약품 코퍼스 등록 구성",
      "Grounded AI configuration": "근거 기반 AI 구성",
      "Semantic retrieval configuration": "시맨틱 검색 구성",
      "Email delivery configuration": "이메일 발송 구성",
      "The backend reports that an AI provider is not configured.": "백엔드에서 AI 공급자가 구성되지 않았다고 보고했습니다.",
      "SMTP sender and delivery are enabled.": "SMTP 발신 계정과 발송이 활성화되었습니다.",
      "SMTP sender exists, but delivery is disabled.": "SMTP 발신 계정은 있지만 발송이 비활성화되었습니다.",
      "The backend reports that an SMTP sender is not configured.": "백엔드에서 SMTP 발신 계정이 구성되지 않았다고 보고했습니다.",
      "Active": "활성",
      "Passing": "통과",
      "SCOPE-01 · deterministic Drug gate": "SCOPE-01 · 결정론적 의약품 게이트",
      "DATA-04 · auth before retrieval": "DATA-04 · 검색 전 권한 확인",
      "AI-03 · evidence grounding": "AI-03 · 증거 근거화",
      "BCP-02 · tested restore": "BCP-02 · 복구 시험",
      "684 active records · 0 leakage indicators": "활성 레코드 684건 · 유출 지표 0건",
      "Cross-user suite passed · build 8a41": "사용자 간 테스트 스위트 통과 · 빌드 8a41",
      "2 outputs correctly withheld": "출력 2건 정상 보류",
      "Restore exercise · 18 Aug 2026": "복구 훈련 · 2026년 8월 18일",
      "18 Aug 2026": "2026년 8월 18일",
      "successful": "성공",
    };
    const compactDuration = value.match(/^(\d+) (sec|min|h)$/);
    const relativeDuration = value.match(/^(\d+) (sec|min|h) ago$/);
    const unit = (raw: string) => raw === "sec" ? "초" : raw === "min" ? "분" : "시간";
    const localizedDuration = relativeDuration
      ? `${relativeDuration[1]}${unit(relativeDuration[2])} 전`
      : compactDuration
        ? `${compactDuration[1]}${unit(compactDuration[2])}`
        : value;
    const fullDate = /^\d{1,2} [A-Z][a-z]{2} \d{4}$/.test(value);
    const isoTimestamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value);
    const isoValue = isoTimestamp && !/(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? `${value}Z` : value;
    const timestampOptions: Intl.DateTimeFormatOptions = {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Seoul",
    };
    const partialDate = value.match(/^(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) · (.+)$/);
    const monthNumber: Record<string, number> = { Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6, Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12 };
    const localizedTemporal = isoTimestamp
      ? formatDate(isoValue, timestampOptions, "ko")
      : fullDate
      ? formatDate(value, { day: "2-digit", month: "short", year: "numeric" }, "ko")
      : partialDate
        ? `${monthNumber[partialDate[2]]}월 ${Number(partialDate[1])}일 · ${partialDate[3]}`
        : localizedDuration;
    const runName = value.match(/^(discovery|reconcile|lifecycle_sweep|backfill|lifecycle|integrity_sample|processing) run$/);
    const runTranslations: Record<string, string> = {
      discovery: "탐색 작업",
      reconcile: "조정 작업",
      lifecycle_sweep: "수명주기 점검 작업",
      backfill: "과거 데이터 수집 작업",
      lifecycle: "수명주기 작업",
      integrity_sample: "무결성 표본 작업",
      processing: "처리 작업",
    };
    const localizedValue = runName
      ? runTranslations[runName[1]]
      : value.startsWith("Prompt ")
        ? `프롬프트 ${value.slice("Prompt ".length)}`
        : localizedTemporal;
    const englishValue = isoTimestamp ? formatDate(isoValue, timestampOptions, "en") : value;
    return text(englishValue, translations[value] ?? localizedValue);
  };

  const submit = () => {
    setError(undefined);
    setNotice(undefined);
    startTransition(async () => {
      try {
        const receipt = await submitReprocess(letterId, reason);
        setNotice({ letterId, jobId: receipt.jobId });
        setLetterId("");
        setReason("");
        setReprocessOpen(false);
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : "";
        setError(
          message === "A letter identifier is required."
            ? "letter_required"
            : message === "A specific operational reason is required."
              ? "reason_required"
              : "request_failed",
        );
      }
    });
  };

  const submitSettings = () => {
    setSettingsError(false);
    setSettingsNotice(false);
    startSettingsTransition(async () => {
      try {
        const confirmed = await saveNotificationSettings(notificationEmail, notificationEnabled);
        setNotification(confirmed);
        setNotificationEmail(confirmed.targetEmail);
        setNotificationEnabled(confirmed.enabled);
        setSettingsNotice(true);
      } catch {
        setSettingsError(true);
      }
    });
  };

  const submitCorpusSync = () => {
    setSyncError(false);
    startSyncTransition(async () => {
      try {
        const receipt = await startCorpusSync();
        setSyncReceipt({ runId: receipt.runId, status: receipt.status });
      } catch {
        setSyncError(true);
      }
    });
  };

  return (
    <div ref={rootRef} className="page-stack admin-page">
      <PageGuide
        className="admin-page__guide"
        title={{ ko: "빠른 시스템 설정", en: "Quick System Settings" }}
        context={{ ko: "권한 작업 · 모든 변경 감사", en: "Privileged operations · every change audited" }}
        description={{
          ko: "알림 수신자, 수집 범위 및 핵심 서비스 상태를 빠르게 확인하고 변경하는 관리자 화면입니다. 상세 운영 증거는 아래 고급 상태에서 확인할 수 있습니다.",
          en: "Review and change notification recipients, corpus windows, and essential service status quickly. Detailed operational evidence remains available under Advanced status.",
        }}
        actions={(
          <>
            <ModeBadge mode={mode} />
            <button ref={reprocessTriggerRef} className="button button--secondary" type="button" onClick={() => setReprocessOpen(true)}><ListRestart size={16} /> {text("Reprocess", "재처리")}</button>
          </>
        )}
      />

      {notice ? <div className="success-toast" role="status"><Check size={16} /><span>{text(`Reprocess job ${notice.jobId} was queued for ${notice.letterId}.`, `${notice.letterId} 재처리 작업을 등록했습니다. 작업 ID: ${notice.jobId}`)}</span><button type="button" aria-label={text("Dismiss", "닫기")} onClick={() => setNotice(undefined)}><X size={14} /></button></div> : null}

      {settingsNotice ? <div className="success-toast" role="status"><Check size={16} /> {text("Notification settings saved and audited.", "알림 설정을 저장하고 감사 기록을 남겼습니다.")}<button type="button" aria-label={text("Dismiss", "닫기")} onClick={() => setSettingsNotice(false)}><X size={14} /></button></div> : null}

      <section className="admin-quick-settings" aria-labelledby="quick-settings-title">
        <header className="admin-quick-settings__header">
          <div><Settings2 size={20} aria-hidden="true" /><div><h2 id="quick-settings-title">{text("Quick settings", "빠른 설정")}</h2><p>{text("The settings used most often are collected here.", "자주 사용하는 시스템 설정만 한곳에 모았습니다.")}</p></div></div>
          <span className="admin-save-state">{settingsPending ? text("Saving…", "저장 중…") : text("Changes are audited", "모든 변경 감사")}</span>
        </header>

        <div className="admin-settings-grid">
          <article className="admin-setting-card admin-setting-card--email">
            <header><span className="admin-setting-card__icon"><BellRing size={19} aria-hidden="true" /></span><div><h3>{text("Warning-letter email", "경고서한 이메일 알림")}</h3><p>{text("Send an email for each newly detected or updated Drug warning letter.", "새로 감지되거나 업데이트된 의약품 경고서한마다 이메일을 보냅니다.")}</p></div></header>
            <label className="admin-toggle-row">
              <span><strong>{text("Automatic email", "자동 이메일")}</strong><small>{deliveryLabel}</small></span>
              <input type="checkbox" checked={notificationEnabled} onChange={(event) => setNotificationEnabled(event.target.checked)} />
            </label>
            <label className="admin-email-field">
              <span>{text("Recipient", "수신 이메일")}</span>
              <div><Mail size={17} aria-hidden="true" /><input type="email" value={notificationEmail} onChange={(event) => setNotificationEmail(event.target.value)} autoComplete="email" /></div>
            </label>
            <div className="admin-delivery-state">
              <span className={deliveryReady ? "is-ready" : "is-attention"}>{deliveryLabel}</span>
              <span>{text(`${notification.queuedDeliveries} queued`, `대기 ${notification.queuedDeliveries}건`)}</span>
              <span>{text(`${notification.failedDeliveries} failed`, `실패 ${notification.failedDeliveries}건`)}</span>
            </div>
            {notification.queuedDeliveries > 0 && !deliveryReady ? <p className="admin-backlog-warning" role="note">{text(
              `${notification.queuedDeliveries} queued alerts may be attempted after SMTP delivery is enabled. Review this backlog before connecting the sender.`,
              `SMTP 발송을 활성화하면 대기 중인 알림 ${notification.queuedDeliveries}건의 발송을 시도할 수 있습니다. 발신 계정을 연결하기 전에 대기 내역을 확인하세요.`,
            )}</p> : null}
            {!deliveryReady ? <details className="admin-sender-help"><summary>{text("How to connect the sender", "발신 계정 연결 방법")}</summary><p>{text("Configure the approved SMTP host and sender address in the server secret manager, enable SMTP delivery, restart the worker, and then verify this status before relying on alerts.", "승인된 SMTP 호스트와 발신 주소를 서버 비밀 관리 시스템에 등록하고 SMTP 발송을 활성화한 뒤 작업자를 재시작하세요. 이 상태가 ‘발송 가능’으로 바뀐 후 알림을 사용하세요.")}</p><code>SMTP_HOST · SMTP_FROM_EMAIL · SMTP_ENABLED</code></details> : null}
            {settingsError ? <p className="admin-settings-error" role="alert">{text("The settings were not confirmed. Check the email and backend connection, then retry.", "설정 저장이 확인되지 않았습니다. 이메일과 백엔드 연결을 확인한 뒤 다시 시도하세요.")}</p> : null}
            <button className="button button--primary" type="button" disabled={settingsPending || !notificationEmail.trim()} onClick={submitSettings}><Save size={16} aria-hidden="true" /> {settingsPending ? text("Saving…", "저장 중…") : text("Save email settings", "이메일 설정 저장")}</button>
          </article>

          <article className="admin-setting-card admin-setting-card--corpus">
            <header><span className="admin-setting-card__icon"><Database size={19} aria-hidden="true" /></span><div><h3>{text("Rolling data window", "데이터 보관 범위")}</h3><p>{text("Automatic discovery and active-corpus retention boundaries.", "자동 수집 및 활성 코퍼스 보관 기준입니다.")}</p></div></header>
            <div className="admin-window-values">
              <div><CalendarRange size={18} aria-hidden="true" /><span>{text("Initial backfill", "초기 수집")}</span><strong>{data.corpus.backfillYears}{text(" years", "년")}</strong><small>{text("Most recent letters", "최근 경고서한")}</small></div>
              <div><ArchiveRestore size={18} aria-hidden="true" /><span>{text("Active retention", "활성 보관")}</span><strong>{data.corpus.activeRetentionYears}{text(" years", "년")}</strong><small>{text("Then retired from search", "이후 검색에서 제외")}</small></div>
            </div>
            <p className="admin-setting-note">{text("Expired records leave browsing and AI retrieval, while source and audit evidence remain retained.", "만료된 기록은 탐색과 AI 검색에서 제외되지만 원문 및 감사 근거는 보존됩니다.")}</p>
            {syncError ? <p className="admin-settings-error" role="alert">{text("The sync was not queued. Check the backend worker and retry.", "동기화 작업을 대기열에 넣지 못했습니다. 백엔드 작업자를 확인한 뒤 다시 시도하세요.")}</p> : null}
            <button className="button button--secondary admin-corpus-sync" type="button" disabled={syncPending || Boolean(syncReceipt) || mode !== "live"} onClick={submitCorpusSync}>
              {syncReceipt ? <Check size={16} aria-hidden="true" /> : <RefreshCcw className={syncPending ? "spin" : undefined} size={16} aria-hidden="true" />}
              {syncPending ? text("Queuing…", "대기열 등록 중…") : syncReceipt ? text("Sync queued", "동기화 대기 중") : text("Run 3-year sync", "3년치 동기화 실행")}
            </button>
            {syncReceipt ? <p className="admin-job-receipt" role="status"><strong>{text("Run ID", "실행 ID")}</strong><code>{syncReceipt.runId}</code><span>{text(`Status: ${syncReceipt.status}`, `상태: ${syncReceipt.status}`)}</span></p> : null}
          </article>

          <article className="admin-setting-card admin-setting-card--service">
            <header><span className="admin-setting-card__icon"><ServerCog size={19} aria-hidden="true" /></span><div><h3>{text("Service essentials", "서비스 핵심 상태")}</h3><p>{text("Read-only checks for the connected AI and delivery path.", "연결된 AI와 알림 경로의 읽기 전용 상태입니다.")}</p></div></header>
            <dl className="admin-essential-list">
              <div><dt>{text("AI model", "AI 모델")}</dt><dd>{data.versions.find((version) => version.component === "Grounded answer model")?.version ?? text("Not configured", "구성되지 않음")}</dd></div>
              <div><dt>{text("Email target", "이메일 수신자")}</dt><dd>{notification.targetEmail}</dd></div>
              <div><dt>{text("Delivery", "발송 상태")}</dt><dd className={emailOperational ? "is-ready" : "is-attention"}>{deliveryLabel}</dd></div>
            </dl>
          </article>
        </div>
      </section>

      <details className="admin-advanced">
        <summary><span><ServerCog size={19} aria-hidden="true" /><span><strong>{text("Advanced system status", "고급 시스템 상태")}</strong><small>{text("Pipelines, queues, controls, and operational evidence", "파이프라인, 대기열, 통제 및 운영 근거")}</small></span></span><span>{text("Open", "열기")}</span></summary>
        <div className="admin-advanced__body">

      <section className="ops-status dossier-reveal dossier-reveal--delay-1">
        <div className="ops-status__overall"><span className={hasOperationalAttention ? "attention-pulse" : "live-pulse"} /><div><span>{text("Connected service report", "연결 서비스 보고")}</span><strong>{overallServiceLabel}</strong><small>{lastAssessed ? text(`Latest reported check: ${lastAssessed}`, `최근 보고 점검: ${adminValue(lastAssessed)}`) : text("No assessment timestamp was returned.", "평가 시각이 반환되지 않았습니다.")}</small></div></div>
        <div><Database size={18} /><span>{text("Backup telemetry", "백업 원격 측정")}</span><strong>{adminValue(data.backupAge)}</strong><small>{text("Read-only backend report", "백엔드 읽기 전용 보고")}</small></div>
        <div><ArchiveRestore size={18} /><span>{text("Restore-test telemetry", "복구 시험 원격 측정")}</span><strong>{adminValue(data.lastRestoreTest.split(" · ")[0])}</strong><small>{adminValue(data.lastRestoreTest.split(" · ")[1] ?? text("No evidence link reported", "보고된 증거 링크 없음"))}</small></div>
        <div><LockKeyhole size={18} /><span>{text("Reported exceptions", "보고된 예외")}</span><strong>{text(`${data.exceptions.length} items`, `${data.exceptions.length}건`)}</strong><small>{text("From returned processing runs", "반환된 처리 작업 기준")}</small></div>
      </section>

      <section className="ops-grid dossier-reveal dossier-reveal--delay-2">
        <article className="ops-panel ops-health">
          <SectionHeading index="01" title={text("Pipeline health", "파이프라인 상태")} detail={text("Owned checks · current processing window", "담당 검사 · 현재 처리 구간")} />
          {data.health.length ? <ul>{data.health.map((check, index) => <li key={`${check.name}-${check.checkedAt}-${index}`}><span className={`health-orb health-orb--${check.status}`} /> <div><strong>{adminValue(check.name)}</strong><small>{adminValue(check.detail)}</small></div><span>{adminValue(check.checkedAt)}</span></li>)}</ul> : <p className="admin-observation-empty">{text("No processing health checks were returned by the service.", "서비스에서 반환한 처리 상태 점검이 없습니다.")}</p>}
        </article>
        <article className="ops-panel ops-queue">
          <SectionHeading index="02" title={text("Durable queues", "내구성 대기열")} detail={text("Depth and oldest unclaimed item", "대기 깊이 및 가장 오래된 미처리 항목")} />
          {data.queue.length ? <div className="queue-table"><header><span>{text("Queue", "대기열")}</span><span>{text("Depth", "대기 수")}</span><span>{text("Oldest", "최장 대기")}</span><span>{text("Status", "상태")}</span></header>{data.queue.map((queue) => <div key={queue.name}><code>{queue.name}</code><strong>{queue.depth}</strong><span>{adminValue(queue.oldest)}</span><em className={queue.status !== "Nominal" ? "attention" : ""}>{adminValue(queue.status)}</em></div>)}</div> : <p className="admin-observation-empty">{text("No queue-depth telemetry was returned by the service.", "서비스에서 반환한 대기열 깊이 정보가 없습니다.")}</p>}
        </article>
      </section>

      <section className="ops-grid ops-grid--lower dossier-reveal dossier-reveal--delay-3">
        <article className="ops-panel ops-exceptions">
          <SectionHeading index="03" title={text("Reported exceptions", "보고된 예외")} detail={text("Exceptions returned by the connected processing service", "연결된 처리 서비스에서 반환한 예외")} />
          {data.exceptions.length ? <ol>{data.exceptions.map((exception) => <li key={exception.id}><AlertTriangle size={17} /><div><div><code>{exception.id}</code><strong>{adminValue(exception.type)}</strong></div><p>{adminValue(exception.detail)}</p><small>{adminValue(exception.source)} · {adminValue(exception.detectedAt)}</small></div></li>)}</ol> : <p className="admin-observation-empty">{text("No processing exceptions were returned.", "반환된 처리 예외가 없습니다.")}</p>}
        </article>
        <article className="ops-panel ops-versions">
          <SectionHeading index="04" title={text("Active controlled versions", "활성 통제 버전")} detail={text("Behavior-changing components", "동작을 변경하는 구성요소")} />
          <ol>{data.versions.map((version) => <li key={version.component}><PackageCheck size={16} /><div><span>{adminValue(version.component)}</span><code>{adminValue(version.version)}</code></div><small>{adminValue(version.activatedAt)}</small><strong>{adminValue(version.status)}</strong></li>)}</ol>
        </article>
      </section>

      <article className="ops-panel control-evidence dossier-reveal dossier-reveal--delay-3">
        <SectionHeading index="05" title={text("Control evidence", "통제 증거")} detail={text("Current operational assertions; open retained evidence before relying on a status", "현재 운영 확인 사항입니다. 상태를 신뢰하기 전에 보존된 증거를 여세요")} />
        {data.controls.length ? <div className="control-grid">{data.controls.map((control) => <section key={control.control}><header>{control.status === "Passing" ? <CheckCircle2 size={17} /> : <CircleAlert size={17} />}<span>{adminValue(control.status)}</span></header><h3>{adminValue(control.control)}</h3><p>{adminValue(control.evidence)}</p></section>)}</div> : <p className="admin-observation-empty">{text("The service did not return linked control evidence. No compliance state is inferred.", "서비스에서 연결된 통제 증거를 반환하지 않았습니다. 규정 준수 상태를 추정하지 않습니다.")}</p>}
      </article>

      <footer className="privileged-warning"><ShieldCheck size={17} /><p><strong>{text("Separation of duties.", "직무를 분리합니다.")}</strong> {text(
        "Administrators can reprocess source versions but cannot silently approve regulatory content. All privileged changes are independently authorized and audited.",
        "관리자는 원문 버전을 재처리할 수 있지만 규제 콘텐츠를 별도 기록 없이 승인할 수 없습니다. 모든 권한 변경은 독립적으로 승인되고 감사됩니다.",
      )}</p></footer>
        </div>
      </details>

      {reprocessOpen ? <div ref={scrimRef} className="modal-scrim" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setReprocessOpen(false); }}><section ref={dialogRef} className="modal-card" role="dialog" aria-modal="true" aria-labelledby="reprocess-title" tabIndex={-1}>
        <header><div><p className="eyebrow">{text("Audited administrative action", "감사되는 관리자 작업")}</p><h2 id="reprocess-title">{text("Reprocess a Drug letter", "의약품 경고서 재처리")}</h2></div><button type="button" aria-label={text("Close", "닫기")} onClick={() => setReprocessOpen(false)}><X size={18} /></button></header>
        <div className="modal-warning"><AlertTriangle size={17} /><p>{text("This creates a new processing job/version. Existing source evidence and prior outputs are retained.", "새 처리 작업과 버전이 생성됩니다. 기존 원문 증거와 이전 출력은 보존됩니다.")}</p></div>
        <label><span>{text("Letter UUID or MARCS-CMS", "경고서 UUID 또는 MARCS-CMS")}</span><input autoFocus value={letterId} onChange={(event) => setLetterId(event.target.value)} placeholder={text("Record identifier", "레코드 식별자")} /></label>
        <label><span>{text("Operational reason", "운영 사유")}</span><textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder={text("Describe the exception, correction, or authorized change…", "예외, 수정 또는 승인된 변경 사항을 설명하세요…")} /></label>
        {error ? <div className="inline-error" role="alert"><CircleAlert size={15} /> {error === "letter_required" ? text("A letter identifier is required.", "경고서 식별자가 필요합니다.") : error === "reason_required" ? text("A specific operational reason is required.", "구체적인 운영 사유가 필요합니다.") : text("The service did not confirm a reprocessing job. Check the queue or audit trail before retrying.", "서비스에서 재처리 작업을 확인하지 못했습니다. 다시 시도하기 전에 대기열 또는 감사 추적을 확인하세요.")}</div> : null}
        <footer><button className="button button--quiet" type="button" onClick={() => setReprocessOpen(false)}>{text("Cancel", "취소")}</button><button className="button button--primary" type="button" disabled={pending || !letterId.trim() || reason.trim().length < 8} onClick={submit}>{pending ? <RefreshCcw className="spin" size={15} /> : <Activity size={15} />} {pending ? text("Submitting…", "제출 중…") : text("Submit reprocess", "재처리 제출")}</button></footer>
      </section></div> : null}
    </div>
  );
}
