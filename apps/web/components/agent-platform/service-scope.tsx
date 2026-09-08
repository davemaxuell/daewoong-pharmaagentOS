"use client";

import { ChevronDown, Database, Info, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import styles from "./service-scope.module.css";

export function ServiceScope() {
  const { text } = useI18n();
  return <div className={styles.scope}>
    <ul className={styles.facts} aria-label={text("Research scope", "리서치 범위")}>
      <li><Database size={17} aria-hidden="true" />{text("Saved FDA sources", "저장된 FDA 자료")}</li>
      <li><ShieldCheck size={17} aria-hidden="true" />{text("Human review required", "담당자 검토 필요")}</li>
    </ul>
    <details className={styles.details}>
      <summary><Info size={16} aria-hidden="true" />{text("Scope & saving", "이용 범위와 저장")}<ChevronDown size={15} aria-hidden="true" /></summary>
      <dl>
        <div><dt>{text("Research tasks", "리서치 작업")}</dt><dd>{text("Saved on the service; reopen in the same browser session.", "서비스에 저장 · 같은 브라우저 세션에서 다시 열기")}</dd></div>
        <div><dt>{text("Keep a copy", "브리핑 보관")}</dt><dd>{text("Download before clearing cookies or switching browsers.", "쿠키 삭제나 브라우저 변경 전 다운로드")}</dd></div>
        <div><dt>{text("Not available yet", "아직 제공하지 않음")}</dt><dd>{text("Automatic FDA updates · Internal SOP analysis", "FDA 자료 자동 업데이트 · 내부 SOP 분석")}</dd></div>
        <div><dt>{text("Decisions", "최종 판단")}</dt><dd>{text("Check FDA originals. AI drafts do not approve compliance or actions.", "FDA 원문 대조 필요 · AI 초안은 규정 준수 판단이나 조치 승인이 아님")}</dd></div>
      </dl>
    </details>
  </div>;
}
