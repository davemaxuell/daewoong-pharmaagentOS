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
        <h1>{text("FDA questions, made easier.", "FDA 자료, 혼자 읽지 마세요.")}</h1>
        <p>{text("Ask in your own words. The AI finds relevant warning letters and explains the evidence, so you can prepare your next review.", "평소 쓰는 말로 질문하세요. AI가 관련 경고서한을 찾아 근거와 함께 설명하고, 다음 검토를 준비하도록 도와드립니다.")}</p>
        <Link href="/ask" className={`button button--primary ${styles.start}`}>
          <MessageSquareText size={21} aria-hidden="true" />
          {text("Ask the AI", "AI에게 질문하기")}
          <ArrowRight size={20} aria-hidden="true" />
        </Link>
        <span className={styles.hint}>{text("No setup needed. Korean or English is fine.", "설정 없이 바로 시작 · 한국어로 편하게 질문하세요")}</span>
      </header>

      <section className={styles.examples} aria-labelledby="examples-heading">
        <h2 id="examples-heading">{text("Not sure what to ask? Start here.", "무엇을 물어볼지 고민된다면")}</h2>
        <p>{text("Choose an example, edit the question, then send it.", "예시를 선택하고, 질문을 원하는 대로 바꾼 뒤 보내세요.")}</p>
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
        <h2 id="how-heading">{text("From question to evidence", "질문하면 이렇게 도와드려요")}</h2>
        <ol>
          <li><strong>{text("You ask", "질문하기")}</strong><p>{text("Name a topic or open a letter you want to understand.", "궁금한 주제를 적거나 살펴볼 경고서한을 선택하세요.")}</p></li>
          <li><strong>{text("AI finds and explains", "AI가 찾아 설명하기")}</strong><p>{text("It searches the saved FDA sources and prepares an answer with references.", "저장된 FDA 자료를 찾아 원문 근거와 함께 답변을 정리합니다.")}</p></li>
          <li><strong>{text("You check the source", "원문 확인하기")}</strong><p>{text("Open the numbered references, then ask a follow-up question. Your team makes the final decision.", "답변의 출처 번호로 원문을 확인하고 이어서 질문하세요. 최종 판단은 담당자가 합니다.")}</p></li>
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
