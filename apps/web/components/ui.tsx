import { DatabaseZap, LockKeyhole } from "lucide-react";
import { formatPortalDate } from "@/lib/date-format";
import { BilingualText, type Locale } from "@/lib/i18n";
import type { DataMode, ReviewState } from "@/lib/types";

export function PageHeader({
  eyebrow,
  title,
  description,
  mode,
  actions,
}: {
  eyebrow: React.ReactNode;
  title: React.ReactNode;
  description: React.ReactNode;
  mode?: DataMode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="page-header dossier-reveal">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-header__description">{description}</p>
      </div>
      <div className="page-header__actions">
        {mode ? <ModeBadge mode={mode} /> : null}
        {actions}
      </div>
    </header>
  );
}

export function ModeBadge({ mode }: { mode: DataMode }) {
  return mode === "live" ? (
    <span className="mode-badge mode-badge--live">
      <span className="live-pulse" aria-hidden="true" />
      <BilingualText en="Live service" ko="실시간 서비스" />
    </span>
  ) : (
    <span className="mode-badge mode-badge--seeded">
      <DatabaseZap size={14} aria-hidden="true" />
      <BilingualText en="Preview data" ko="미리보기 데이터" />
      <span className="sr-only">
        <BilingualText
          en="The API is not configured or unavailable; isolated preview records are displayed."
          ko="API가 구성되지 않았거나 사용할 수 없어 격리된 미리보기 레코드를 표시합니다."
        />
      </span>
    </span>
  );
}

export function ScopeBadge({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`scope-badge${compact ? " scope-badge--compact" : ""}`}>
      <LockKeyhole size={13} aria-hidden="true" />
      <BilingualText en="FDA Product: Drugs" ko="FDA 제품: 의약품" />
    </span>
  );
}

const statusLabels: Record<string, { en: string; ko: string }> = {
  pending: { en: "Pending", ko: "검토 대기" },
  auto_approved: { en: "Auto approved", ko: "자동 승인" },
  approved: { en: "Approved", ko: "승인됨" },
  needs_revision: { en: "Needs revision", ko: "수정 필요" },
  rejected: { en: "Rejected", ko: "거부됨" },
  new: { en: "New", ko: "신규" },
  updated: { en: "Updated", ko: "업데이트됨" },
  response_added: { en: "Response added", ko: "답변 추가" },
  closeout_added: { en: "Closeout added", ko: "종결서 추가" },
  restored: { en: "Restored", ko: "복원됨" },
  healthy: { en: "Healthy", ko: "정상" },
  attention: { en: "Attention", ko: "주의" },
  degraded: { en: "Degraded", ko: "성능 저하" },
  active: { en: "Active", ko: "활성" },
  running: { en: "Running", ko: "실행 중" },
  queued: { en: "Queued", ko: "대기열" },
  failed: { en: "Failed", ko: "실패" },
  withheld: { en: "Withheld", ko: "보류" },
};

export function StatusPill({ state }: { state: ReviewState | string }) {
  const key = state.toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
  const normalized = key.replaceAll("_", "-");
  const fallback = state.replaceAll("_", " ");
  const label = statusLabels[key] ?? { en: fallback, ko: fallback };

  return (
    <span className={`status-pill status-pill--${normalized}`}>
      <BilingualText en={label.en} ko={label.ko} />
    </span>
  );
}

export function formatDate(
  date: string,
  options?: Intl.DateTimeFormatOptions,
  locale: Locale = "en",
) {
  return formatPortalDate(date, options, locale);
}

export function SectionHeading({
  index,
  title,
  detail,
  action,
}: {
  index?: string;
  title: React.ReactNode;
  detail?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        {index ? <span className="section-heading__index">{index}</span> : null}
        <div>
          <h2>{title}</h2>
          {detail ? <p>{detail}</p> : null}
        </div>
      </div>
      {action}
    </div>
  );
}

export function PaperPanel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`paper-panel ${className}`.trim()}>{children}</section>;
}
