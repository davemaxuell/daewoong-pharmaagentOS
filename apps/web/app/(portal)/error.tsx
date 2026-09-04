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
      <h1>{text("The live FDA data could not be loaded.", "실시간 FDA 데이터를 불러오지 못했습니다.")}</h1>
      <p>
        {text(
          "No preview records were substituted. Retry the connection; if it continues, ask the service administrator to check the API and worker.",
          "미리보기 레코드로 대체하지 않았습니다. 연결을 다시 시도하고, 문제가 계속되면 서비스 관리자에게 API와 작업자 상태를 확인해 달라고 요청하세요.",
        )}
      </p>
      <div>
        <button className="button button--primary" type="button" onClick={reset}>
          <RotateCcw size={16} aria-hidden="true" /> {text("Retry view", "보기 다시 시도")}
        </button>
        <Link className="button button--secondary" href="/drug-letters">
          <ArrowLeft size={16} aria-hidden="true" /> {text("Drug Letters", "의약품 경고서한")}
        </Link>
      </div>
      <small>
        <ShieldCheck size={14} aria-hidden="true" />
        {text("This read failure did not change source or audit records.", "이 조회 실패로 원본 또는 감사 레코드가 변경되지 않았습니다.")}
      </small>
    </section>
  );
}
