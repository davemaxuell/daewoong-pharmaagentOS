"use client";

import Link from "next/link";
import { ArrowLeft, RotateCcw } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export default function PortalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { text } = useI18n();

  return (
    <section className="portal-error" role="alert">
      <span className="portal-error__seal" aria-hidden="true">!</span>
      <h1>{text("We couldn’t load this page’s data", "지금은 자료를 불러올 수 없어요")}</h1>
      <p>
        {text(
          "The data service is unavailable. You can try again or prepare a review request from the home page. Your saved browser drafts are still available.",
          "자료 서비스에 연결할 수 없습니다. 다시 시도하거나 홈에서 검토 요청을 준비해주세요. 이 브라우저에 저장한 초안은 계속 이용할 수 있습니다.",
        )}
      </p>
      <div>
        <button className="button button--primary" type="button" onClick={reset}>
          <RotateCcw size={16} aria-hidden="true" /> {text("Try again", "다시 시도")}
        </button>
        <Link className="button button--secondary" href="/dashboard">
          <ArrowLeft size={16} aria-hidden="true" /> {text("Prepare a request", "검토 요청 작성하기")}
        </Link>
      </div>
      <Link href="/help#availability">{text("See what you can use now", "지금 이용할 수 있는 기능 보기")}</Link>
    </section>
  );
}
