"use client";

import Link from "next/link";
import { ArrowLeft, RotateCcw, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export default function PortalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { text } = useI18n();

  return (
    <section className="portal-error" role="alert">
      <span className="portal-error__seal" aria-hidden="true">!</span>
      <p className="eyebrow">{text("Live service unavailable", "실시간 서비스 연결 안 됨")}</p>
      <h1>{text("This workspace could not load its data.", "워크스페이스 데이터를 불러오지 못했습니다.")}</h1>
      <p>
        {text(
          "The connected service is unavailable. Try again, or return to the agent workspace to prepare a local review brief.",
          "연결된 서비스를 사용할 수 없습니다. 다시 시도하거나 에이전트 워크스페이스에서 브라우저 검토 초안을 준비하세요.",
        )}
      </p>
      <div>
        <button className="button button--primary" type="button" onClick={reset}>
          <RotateCcw size={16} aria-hidden="true" /> {text("Retry view", "보기 다시 시도")}
        </button>
        <Link className="button button--secondary" href="/dashboard">
          <ArrowLeft size={16} aria-hidden="true" /> {text("Agent workspace", "에이전트 워크스페이스")}
        </Link>
      </div>
      <small>
        <ShieldCheck size={14} aria-hidden="true" />
        {text("This read failure did not change source or audit records.", "이 조회 실패로 원본 또는 감사 레코드가 변경되지 않았습니다.")}
      </small>
    </section>
  );
}
