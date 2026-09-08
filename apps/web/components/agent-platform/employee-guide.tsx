"use client";

import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import styles from "./employee-guide.module.css";

export function EmployeeGuide() {
  const { text } = useI18n();
  const steps = [
    ["Ask in your own words", "평소 쓰는 말로 질문하세요", "Name a topic such as cleaning validation, or choose an example. You can edit it before sending. The AI settings are already chosen for you.", "세척 밸리데이션처럼 궁금한 주제를 적거나 예시를 선택하세요. 보내기 전에 수정할 수 있습니다. AI 설정은 자동으로 선택됩니다."],
    ["Read the answer and its sources", "답변과 원문을 함께 확인하세요", "The AI searches saved FDA letters and explains relevant findings. Open the numbered references beside the answer to see the supporting passages.", "AI가 저장된 FDA 경고서한을 검색하고 관련 지적 사항을 설명합니다. 답변의 출처 번호를 누르면 근거가 된 원문을 확인할 수 있습니다."],
    ["Ask a follow-up", "이어서 질문하세요", "Try ‘Explain that more simply’ or ‘What should our team check?’ Stay in the same conversation to keep the context.", "‘더 쉽게 설명해줘’ 또는 ‘우리 팀에서 무엇을 확인해야 할까?’라고 물어보세요. 같은 대화에서 질문하면 앞선 내용을 이어서 살펴볼 수 있습니다."],
  ];
  const questions = [
    ["Do I need to know how AI works?", "AI를 잘 몰라도 사용할 수 있나요?", "You can start without any AI knowledge. Write a normal question. Search and answer options are optional; the default settings are enough to begin.", "네. AI 지식 없이도 평소처럼 질문하면 됩니다. 검색·답변 설정은 선택 사항이며 처음에는 바꿀 필요가 없습니다."],
    ["How do I ask about one particular letter?", "특정 경고서한만 질문하려면 어떻게 하나요?", "Find the company in the FDA letter library, open its letter, and choose the AI question action. The selected letter appears above the question box so you can see which source is being used.", "‘FDA 경고서한 찾기’에서 회사명을 검색하고 경고서한을 연 뒤 AI 질문 버튼을 누르세요. 질문 입력창 위에 선택한 경고서한이 표시됩니다."],
    ["Where can I find my previous work?", "이전 작업은 어디에서 찾나요?", "Previous AI conversations are in the sidebar’s chat history. Bookmarked letters are in Saved sources. Review drafts are separate notes stored only in this browser; open My review drafts from Home or the additional menu. Download drafts you need to keep before clearing browser data.", "이전 AI 대화는 메뉴의 대화 기록에서, 즐겨찾기한 경고서한은 ‘저장한 자료’에서 확인하세요. ‘내 검토 초안’은 별도로 이 브라우저에만 저장하는 메모이며 홈 하단이나 추가 메뉴에서 열 수 있습니다. 브라우저 데이터를 삭제하기 전 필요한 초안을 다운로드하세요."],
    ["Are new FDA letters added automatically?", "새 FDA 경고서한도 자동으로 들어오나요?", "Not yet. Search and AI answers use the FDA documents already saved in the database. Automatic collection of new letters is not enabled.", "아직은 아닙니다. 검색과 AI 답변은 현재 데이터베이스에 저장된 FDA 자료를 사용합니다. 새 경고서한 자동 수집은 아직 켜져 있지 않습니다."],
    ["What if an answer or source does not load?", "답변이나 자료가 나오지 않으면 어떻게 하나요?", "If an answer fails, retry the question. If no evidence is found, use a more specific topic or select a letter from the library. If a page fails to load, reload it; if the problem continues, tell your service administrator which page you were using.", "답변에 실패하면 질문을 다시 시도하세요. 근거를 찾지 못하면 주제를 더 구체적으로 적거나 자료실에서 경고서한을 선택하세요. 페이지가 열리지 않으면 새로고침하고, 문제가 계속되면 사용 중이던 페이지를 서비스 담당자에게 알려주세요."],
    ["Can AI review our internal documents or approve a decision?", "내부 문서 검토나 승인도 AI가 해주나요?", "Internal-document analysis and automated specialist reviews are still being prepared. Current AI answers help you understand FDA evidence and prepare review questions. Your company’s qualified reviewers make compliance decisions and approve actions.", "내부 문서 분석과 전문 에이전트의 자동 검토는 준비 중입니다. 현재 AI는 FDA 근거를 이해하고 검토 질문을 준비하도록 돕습니다. 규정 준수 판단과 조치 승인은 회사의 담당자가 수행합니다."],
  ];
  return (
    <article className={styles.guide}>
      <header>
        <p>{text("Quick guide", "이용 방법")}</p>
        <h1>{text("Your first question is enough to start.", "질문 하나면 시작할 수 있어요.")}</h1>
        <p>{text("PharmaAgent OS helps you find and understand FDA warning-letter evidence. You ask; the AI searches and explains; your team reviews the result.", "PharmaAgent OS는 FDA 경고서한의 근거를 찾고 이해하도록 돕습니다. 질문하면 AI가 찾아 설명하고, 담당자가 결과를 검토합니다.")}</p>
        <Link className="button button--primary" href="/ask">{text("Ask my first question", "첫 질문 해보기")}<ArrowRight size={18} aria-hidden="true" /></Link>
      </header>
      <section aria-labelledby="steps-heading">
        <h2 id="steps-heading">{text("Three simple steps", "이렇게 사용하세요")}</h2>
        <ol className={styles.steps}>{steps.map(([en, ko, bodyEn, bodyKo], index) => <li key={en}><span>{index + 1}</span><div><h3>{text(en, ko)}</h3><p>{text(bodyEn, bodyKo)}</p></div></li>)}</ol>
      </section>
      <section className={styles.example}>
        <span>{text("An example you can try", "이렇게 질문해보세요")}</span>
        <blockquote>{text("Find FDA findings about cleaning validation. Explain them simply and show the original evidence.", "세척 밸리데이션 관련 FDA 지적 사항을 찾아주세요. 쉬운 말로 설명하고 원문 근거도 보여주세요.")}</blockquote>
        <Link href="/ask?starter=understand">{text("Use this example", "이 예시로 시작하기")}</Link>
      </section>
      <section id="availability" className={styles.availability}>
        <h2>{text("What works today", "지금 이용할 수 있는 기능")}</h2>
        <p>{text("Search saved FDA letters, read original documents, ask the AI for answers with references, and save sources for later. Review drafts remain personal notes, not submitted AI tasks.", "저장된 FDA 경고서한 검색, 원문 읽기, 출처가 포함된 AI 답변, 자료 즐겨찾기를 이용할 수 있습니다. 검토 초안은 개인 메모이며 AI 작업으로 제출되지 않습니다.")}</p>
      </section>
      <section className={styles.faq}>
        <h2>{text("Common questions", "자주 묻는 질문")}</h2>
        {questions.map(([en, ko, bodyEn, bodyKo]) => <details key={en}><summary>{text(en, ko)}</summary><p>{text(bodyEn, bodyKo)}</p></details>)}
      </section>
      <footer><ShieldCheck size={20} aria-hidden="true" /><p>{text("AI answers can contain mistakes. Check the original evidence before using an answer in a work decision.", "AI 답변에는 오류가 있을 수 있습니다. 업무 판단에 활용하기 전 원문 근거를 확인하세요.")}</p></footer>
    </article>
  );
}
