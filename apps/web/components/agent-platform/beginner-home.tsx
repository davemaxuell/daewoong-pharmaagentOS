"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ArrowRight, FileSearch, GitCompareArrows, ListChecks, MessageSquareText, Network } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { beginnerPrompts } from "@/lib/beginner-prompts";
import { ResearchJourney } from "./research-journey";
import { ServiceScope } from "./service-scope";
import styles from "./beginner-home.module.css";

const taskIcons = [FileSearch, GitCompareArrows, ListChecks];

export function BeginnerHome() {
  const { text, locale } = useI18n();
  const router = useRouter();
  useEffect(() => {
    if (window.location.hash === "#saved-requests") router.replace("/requests#saved-requests");
  }, [router]);
  return <div className={styles.home}>
    <header className={styles.intro}>
      <p className={styles.byline}>{text("Daewoong · FDA research", "대웅 · FDA 리서치")}</p>
      <h1>{text("Your goal. An evidence-backed brief.", "목표를 입력하면, 근거 있는 브리핑으로.")}</h1>
      <ResearchJourney />
      <div className={styles.entryActions}>
        <Link href="/research" className={`button button--primary ${styles.start}`}><Network size={22} aria-hidden="true" />{text("Start agent research", "에이전트 리서치 시작")}<ArrowRight size={20} aria-hidden="true" /></Link>
        <span className={styles.hint}>{text("Korean or English · No setup", "한국어·영어 지원 · 별도 설정 없음")}</span>
      </div>
    </header>

    <section aria-labelledby="examples-heading">
      <div className={styles.sectionHeading}><h2 id="examples-heading">{text("Quick questions", "간단한 질문")}</h2><Link href="/ask"><MessageSquareText size={17} aria-hidden="true" />{text("Open AI chat", "AI 대화 열기")}</Link></div>
      <div className={styles.tasks}>{beginnerPrompts.map((task, index) => {
        const Icon = taskIcons[index];
        return <Link key={task.id} href={`/ask?starter=${task.id}`}><Icon size={23} aria-hidden="true" /><strong>{task.title[locale]}</strong><ArrowRight size={20} aria-hidden="true" /></Link>;
      })}</div>
    </section>

    <Link className={styles.library} href="/drug-letters"><FileSearch size={25} aria-hidden="true" /><span><strong>{text("Find an FDA letter", "FDA 경고서한 찾기")}</strong><small>{text("Search by company or topic", "회사명이나 주제로 검색")}</small></span><ArrowRight size={20} aria-hidden="true" /></Link>
    <ServiceScope />
    <footer className={styles.footer}><Link href="/help">{text("Quick guide", "이용 방법")}</Link><Link href="/requests#saved-requests">{text("My review drafts", "내 검토 초안")}</Link></footer>
  </div>;
}
