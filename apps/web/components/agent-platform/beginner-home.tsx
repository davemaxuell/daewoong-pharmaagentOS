"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ArrowRight, FileText, MessageSquareText } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { beginnerPrompts } from "@/lib/beginner-prompts";
import styles from "./beginner-home.module.css";

export function BeginnerHome() {
  const { text, locale } = useI18n();
  const router = useRouter();
  useEffect(() => {
    if (window.location.hash === "#saved-requests") router.replace("/requests#saved-requests");
  }, [router]);
  return (
    <div className={styles.home}>
      <header className={styles.intro}>
        <p className={styles.byline}>{text("Daewoong · FDA research assistant", "대웅 · FDA 업무 도우미")}</p>
        <h1>{text("Give your FDA research a goal.", "FDA 리서치, 목표만 알려 주세요.")}</h1>
        <p>{text("Your research agent plans the work, reads FDA sources, checks its findings, and prepares a review brief. Follow each action as it happens.", "리서치 에이전트가 계획을 세우고 FDA 원문을 읽어 근거를 검토한 뒤 브리핑을 준비합니다. 작업 과정을 실시간으로 확인하세요.")}</p>
        <Link href="/research" className={`button button--primary ${styles.start}`}>
          <MessageSquareText size={21} aria-hidden="true" />
          {text("Start agent research", "에이전트 리서치 시작")}
          <ArrowRight size={20} aria-hidden="true" />
        </Link>
        <span className={styles.hint}>{text("No setup needed. Korean or English is fine.", "설정 없이 바로 시작 · 한국어로 편하게 요청하세요")} <Link href="/ask">{text("Ask a quick question", "간단한 질문하기")}</Link></span>
      </header>

      <section className={styles.examples} aria-labelledby="examples-heading">
        <h2 id="examples-heading">{text("Just need a quick answer?", "간단한 답변이 필요하신가요?")}</h2>
        <p>{text("These examples open quick chat. For a full research brief, start agent research above.", "이 예시는 빠른 질문 화면으로 이동합니다. 전체 조사 브리핑이 필요하면 위의 에이전트 리서치를 시작하세요.")}</p>
        <div className={styles.tasks}>
          {beginnerPrompts.map((task) => (
            <Link key={task.id} href={`/ask?starter=${task.id}`}>
              <span><strong>{task.title[locale]}</strong><small>{task.prompt[locale]}</small></span>
              <ArrowRight size={21} aria-hidden="true" />
            </Link>
          ))}
        </div>
      </section>

      <section className={styles.how} aria-labelledby="how-heading">
        <h2 id="how-heading">{text("From a goal to a review brief", "목표에서 검토 브리핑까지")}</h2>
        <ol>
          <li><strong>{text("Set the goal", "목표 알려주기")}</strong><p>{text("Describe the briefing or comparison your team needs.", "팀에 필요한 브리핑이나 비교 내용을 적어 주세요.")}</p></li>
          <li><strong>{text("Follow the agent’s work", "에이전트 작업 확인하기")}</strong><p>{text("See its plan, searches, source passages, and evidence checks as it works.", "조사 계획과 검색, 원문 확인, 근거 검토 과정을 실시간으로 살펴보세요.")}</p></li>
          <li><strong>{text("Review the saved brief", "저장된 브리핑 검토하기")}</strong><p>{text("Open citations and review the draft with your team. The final decision stays with you.", "출처를 열어 초안을 대조하고 팀과 검토하세요. 최종 판단은 담당자가 합니다.")}</p></li>
        </ol>
      </section>

      <div className={styles.library}>
        <FileText size={24} aria-hidden="true" />
        <div><strong>{text("Looking for a particular company?", "특정 회사의 경고서한을 찾으시나요?")}</strong><p>{text("Find a letter in the library, then ask the AI about that document.", "자료실에서 경고서한을 열고 해당 문서에 대해 AI에게 질문하세요.")}</p></div>
        <Link href="/drug-letters">{text("Browse FDA letters", "FDA 자료 찾기")} <ArrowRight size={18} aria-hidden="true" /></Link>
      </div>
      <footer className={styles.footer}>
        <p>{text("Answers use the saved FDA collection. Automatic updates and internal-document analysis are not enabled yet.", "답변은 저장된 FDA 자료를 바탕으로 합니다. 새 자료 자동 업데이트와 내부 문서 분석은 아직 제공하지 않습니다.")}</p>
        <div><Link href="/help">{text("Quick guide", "이용 방법")}</Link><Link href="/requests#saved-requests">{text("My review drafts", "내 검토 초안")}</Link></div>
      </footer>
    </div>
  );
}
