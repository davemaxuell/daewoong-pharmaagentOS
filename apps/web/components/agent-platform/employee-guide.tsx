"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, Download, FileSearch, MessageSquareText, Network, Play, ShieldCheck, Square } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { ResearchJourney } from "./research-journey";
import { ServiceScope } from "./service-scope";
import styles from "./employee-guide.module.css";

export function EmployeeGuide() {
  const { text } = useI18n();
  const destinations = [
    { icon: Network, href: "/research", title: text("Prepare a research brief", "리서치 브리핑 준비"), detail: text("Agent research · Live progress", "에이전트 조사 · 실시간 진행 확인") },
    { icon: MessageSquareText, href: "/ask", title: text("Ask a quick question", "간단한 질문하기"), detail: text("AI answers · Follow-up questions", "AI 답변 · 이어서 질문") },
    { icon: FileSearch, href: "/drug-letters", title: text("Find an FDA letter", "FDA 경고서한 찾기"), detail: text("Company search · Original documents", "회사명 검색 · 원문 확인") },
  ];
  const controls = [
    { icon: Square, title: text("Stop research", "리서치 중지"), detail: text("Stop further work; retain progress.", "추가 작업 중지 · 진행 내용 보관") },
    { icon: Play, title: text("Resume research", "리서치 이어서 진행"), detail: text("Continue from saved progress.", "저장한 단계부터 다시 진행") },
    { icon: BookOpen, title: text("Source references", "출처 번호"), detail: text("Select S1, S2… to open evidence.", "S1, S2… 선택으로 원문 열기") },
    { icon: Download, title: text("Download", "다운로드"), detail: text("Keep the brief and its sources.", "브리핑과 출처를 파일로 보관") },
  ];
  const questions = [
    ["Will research continue after I close the page?", "페이지를 닫아도 계속 진행되나요?", "Yes. Reopen Research agent in the same browser session to see saved progress and results.", "네. 같은 브라우저 세션에서 리서치 에이전트를 다시 열면 진행 상황과 결과를 확인할 수 있습니다."],
    ["Do I need AI settings or an account?", "AI 설정이나 계정이 필요한가요?", "No. Choose an example or write your goal in Korean or English.", "필요하지 않습니다. 예시를 고르거나 한국어·영어로 목표를 적어 주세요."],
    ["How do I ask about a particular letter?", "특정 경고서한을 질문하려면?", "Find the company in the FDA library, open its letter, then choose the AI question action.", "FDA 자료실에서 회사명 검색 → 경고서한 열기 → AI 질문을 선택하세요."],
    ["Where is my previous work?", "이전 작업은 어디에 있나요?", "Research briefs: Research agent. Conversations: Chat history. Bookmarks: Saved sources. My review drafts holds separate browser-only notes that have not been submitted to the agent.", "브리핑은 리서치 에이전트, 대화는 대화 기록, 즐겨찾기는 저장한 자료에서 찾으세요. ‘내 검토 초안’은 이 브라우저에만 보관하는 별도 메모이며 에이전트에 제출되지 않습니다."],
    ["What if a task or source fails?", "작업이나 자료를 불러오지 못하면?", "Retry or reload. If evidence is insufficient, narrow the topic or select a specific company. Contact your service administrator if the problem continues.", "다시 시도하거나 새로고침하세요. 근거가 부족하면 주제나 회사를 구체적으로 지정하세요. 문제가 계속되면 서비스 담당자에게 알려주세요."],
  ];
  return <article className={styles.guide}>
    <header><h1>{text("Get started in three steps", "세 단계로 시작하기")}</h1><ResearchJourney /><Link className="button button--primary" href="/research">{text("Start agent research", "에이전트 리서치 시작")}<ArrowRight size={18} aria-hidden="true" /></Link></header>
    <section aria-labelledby="guide-destinations"><h2 id="guide-destinations">{text("Choose your task", "필요한 작업 선택")}</h2><div className={styles.destinations}>{destinations.map(({icon: Icon, href, title, detail}) => <Link key={href} href={href}><Icon size={25} aria-hidden="true" /><span><strong>{title}</strong><small>{detail}</small></span><ArrowRight size={19} aria-hidden="true" /></Link>)}</div></section>
    <section aria-labelledby="guide-controls"><h2 id="guide-controls">{text("Controls at a glance", "주요 기능 한눈에 보기")}</h2><dl className={styles.controls}>{controls.map(({icon: Icon, title, detail}) => <div key={title}><dt><Icon size={21} aria-hidden="true" />{title}</dt><dd>{detail}</dd></div>)}</dl></section>
    <section id="availability"><h2>{text("Scope & storage", "이용 범위와 저장")}</h2><ServiceScope /></section>
    <section className={styles.faq}><h2>{text("Common questions", "자주 묻는 질문")}</h2>{questions.map(([en, ko, bodyEn, bodyKo]) => <details key={en}><summary>{text(en, ko)}</summary><p>{text(bodyEn, bodyKo)}</p></details>)}</section>
    <footer><ShieldCheck size={20} aria-hidden="true" /><p>{text("AI drafts can be wrong. Check the FDA originals before use.", "AI 초안에는 오류가 있을 수 있습니다. 사용 전 FDA 원문을 확인하세요.")}</p></footer>
  </article>;
}
