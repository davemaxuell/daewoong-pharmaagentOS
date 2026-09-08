"use client";

import { ArrowRight, FileCheck2, Network, Target } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import styles from "./research-journey.module.css";

/** Explains responsibility and sequence; never represents a running task. */
export function ResearchJourney({ compact = false }: { compact?: boolean }) {
  const { text } = useI18n();
  const steps = [
    { icon: Target, owner: text("You", "담당자"), title: text("Set a goal", "목표 입력"), detail: text("Choose a topic", "조사할 주제 선택") },
    { icon: Network, owner: text("Research agent", "리서치 에이전트"), title: text("Find & check", "조사와 근거 검토"), detail: text("Follow the work live", "작업 과정 실시간 확인") },
    { icon: FileCheck2, owner: text("You", "담당자"), title: text("Review the brief", "브리핑 확인"), detail: text("Check citations · Download", "출처 확인 · 다운로드") },
  ];
  return <ol className={`${styles.journey} ${compact ? styles.compact : ""}`} aria-label={text("How research works", "리서치 이용 순서")}>
    {steps.map(({ icon: Icon, owner, title, detail }, index) => <li key={index}>
      <div className={styles.icon}><Icon size={27} aria-hidden="true" /></div>
      <div><span className={styles.owner}>{owner}</span><strong>{title}</strong>{!compact ? <small>{detail}</small> : null}</div>
      {index < steps.length - 1 ? <ArrowRight className={styles.arrow} size={20} aria-hidden="true" /> : null}
    </li>)}
  </ol>;
}
