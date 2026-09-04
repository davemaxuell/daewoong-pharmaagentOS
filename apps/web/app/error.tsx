"use client";

import { RotateCcw } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { text } = useI18n();

  return (
    <main id="main-content" className="state-page" role="alert" tabIndex={-1}>
      <p className="eyebrow">{text("Application exception", "애플리케이션 오류")}</p>
      <h1>{text("The dossier could not be opened.", "규제 문서를 열 수 없습니다.")}</h1>
      <p>
        {text(
          "The source data remains unchanged. Retry the view or contact the service owner if this persists.",
          "원본 데이터는 변경되지 않았습니다. 다시 시도하고 문제가 계속되면 서비스 담당자에게 문의하세요.",
        )}
      </p>
      <button className="button button--primary" type="button" onClick={reset}>
        <RotateCcw size={16} aria-hidden="true" /> {text("Retry", "다시 시도")}
      </button>
    </main>
  );
}
