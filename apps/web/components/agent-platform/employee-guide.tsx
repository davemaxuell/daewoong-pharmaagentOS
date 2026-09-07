"use client";

import Link from "next/link";
import {
  ArrowRight,
  Check,
  FileText,
  GitBranch,
  ShieldCheck,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";
import styles from "./employee-guide.module.css";

export function EmployeeGuide() {
  const { text } = useI18n();
  return (
    <article className={styles.guide}>
      <header>
        <p>{text("Getting started", "이용 방법")}</p>
        <h1>
          {text(
            "Start with the question you already have.",
            "궁금했던 질문 하나로 시작하세요.",
          )}
        </h1>
        <p>
          {text(
            "PharmaAgent OS helps Daewoong teams prepare reviews of FDA findings. You do not need to choose an AI model or configure an agent.",
            "PharmaAgent OS는 대웅 임직원의 FDA 지적 사항 검토를 돕습니다. AI 모델을 고르거나 에이전트를 설정할 필요가 없습니다.",
          )}
        </p>
        <Link className="button button--primary" href="/dashboard">
          {text("Prepare my first request", "첫 검토 요청 작성하기")}
          <ArrowRight size={18} />
        </Link>
      </header>
      <section aria-labelledby="steps-heading">
        <h2 id="steps-heading">
          {text(
            "Three steps to a useful request",
            "검토 요청은 이렇게 작성하세요",
          )}
        </h2>
        <ol className={styles.steps}>
          <li>
            <span>1</span>
            <div>
              <h3>
                {text("Choose what you need", "필요한 검토를 선택하세요")}
              </h3>
              <p>
                {text(
                  "Understand a warning letter, assess a possible impact, or compare it with a procedure.",
                  "경고서한 핵심 파악, 우리 업무 영향 검토, 내부 절차 비교 중에서 선택하세요.",
                )}
              </p>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <h3>{text("Write your question", "검토할 질문을 적으세요")}</h3>
              <p>
                {text(
                  "Mention the topic, company, or process. Use an example if you are unsure where to start. Add an FDA link if you have one.",
                  "주제, 회사명 또는 검토할 업무를 적어주세요. 막막하다면 ‘예시로 시작’을 눌러보세요. 알고 있는 FDA 링크도 추가할 수 있습니다.",
                )}
              </p>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <h3>
                {text("Save and keep a copy", "초안을 저장하고 보관하세요")}
              </h3>
              <p>
                {text(
                  "Return to your saved draft on the home page, or download a readable request to pass to a colleague through your company’s usual channels.",
                  "홈 화면에서 저장한 초안을 이어서 작성하거나, 읽기 쉬운 요청 파일을 다운로드해 평소 사용하는 사내 채널로 전달하세요.",
                )}
              </p>
            </div>
          </li>
        </ol>
      </section>
      <section className={styles.example}>
        <span>
          {text(
            "Example question · not a real finding",
            "질문 작성 예시 · 실제 지적 사항이 아닙니다",
          )}
        </span>
        <blockquote>
          {text(
            "What should our quality team check about cleaning validation after reading this warning letter? Please list the source passages and questions for our reviewer.",
            "이 경고서한의 세척 밸리데이션 지적 사항과 관련해 우리 품질팀이 무엇을 확인해야 하나요? 원문 근거와 담당자가 검토할 질문을 정리해주세요.",
          )}
        </blockquote>
        <p>
          {text(
            "A specific topic and a clear question are enough to prepare the request. Source evidence is required before a formal analysis.",
            "구체적인 주제와 질문만으로 요청을 준비할 수 있습니다. 정식 분석을 진행하려면 원문 근거가 필요합니다.",
          )}
        </p>
      </section>
      <section id="availability" className={styles.availability}>
        <h2>
          {text("What can I use today?", "지금 어떤 기능을 이용할 수 있나요?")}
        </h2>
        <div className={styles.availabilityColumns}>
          <div>
            <h3>
              <Check size={20} />
              {text("Available now", "지금 이용 가능")}
            </h3>
            <ul>
              <li>
                {text(
                  "Write and edit review requests",
                  "검토 요청 작성 및 수정",
                )}
              </li>
              <li>
                {text(
                  "Save several drafts in this browser",
                  "이 브라우저에 여러 초안 저장",
                )}
              </li>
              <li>
                {text(
                  "Download a readable request file",
                  "읽기 쉬운 요청 파일 다운로드",
                )}
              </li>
              <li>
                {text(
                  "Learn how the specialist agents will help",
                  "전문 에이전트의 역할 확인",
                )}
              </li>
            </ul>
          </div>
          <div>
            <h3>{text("Still being prepared", "준비 중인 기능")}</h3>
            <ul>
              <li>
                {text(
                  "Live FDA source search and evidence answers",
                  "실시간 FDA 자료 검색 및 근거 기반 답변",
                )}
              </li>
              <li>
                {text(
                  "Automated specialist-agent analysis",
                  "전문 에이전트의 자동 분석",
                )}
              </li>
              <li>
                {text(
                  "Shared company records and approval actions",
                  "회사 공용 검토 기록 및 승인 작업",
                )}
              </li>
            </ul>
          </div>
        </div>
        <p>
          {text(
            "A saved request is a draft. Saving or downloading does not submit work or start an analysis.",
            "저장한 요청은 초안입니다. 저장하거나 다운로드해도 작업이 제출되거나 분석이 시작되지는 않습니다.",
          )}
        </p>
      </section>
      <section>
        <h2>{text("Where should I go?", "어떤 메뉴를 사용하면 되나요?")}</h2>
        <div className={styles.destinations}>
          <Link href="/dashboard">
            <FileText size={23} />
            <span>
              <strong>{text("Start a review", "검토 시작하기")}</strong>
              <small>
                {text(
                  "Prepare a question or continue a saved request.",
                  "질문을 작성하거나 저장한 요청을 이어서 작성합니다.",
                )}
              </small>
            </span>
            <ArrowRight size={18} />
          </Link>
          <Link href="/drug-letters">
            <FileText size={23} />
            <span>
              <strong>{text("FDA letter library", "FDA 경고서한 찾기")}</strong>
              <small>
                {text(
                  "Look up letters once the data service is connected.",
                  "자료 서비스가 연결되면 경고서한을 찾아볼 수 있습니다.",
                )}
              </small>
            </span>
            <ArrowRight size={18} />
          </Link>
          <Link href="/agents">
            <GitBranch size={23} />
            <span>
              <strong>{text("Specialist agents", "전문 에이전트")}</strong>
              <small>
                {text(
                  "Optional: see who does what in the planned review.",
                  "예정된 검토에서 각 에이전트가 맡는 일을 알아봅니다.",
                )}
              </small>
            </span>
            <ArrowRight size={18} />
          </Link>
        </div>
      </section>
      <section className={styles.faq}>
        <h2>{text("Common questions", "자주 묻는 질문")}</h2>
        <details>
          <summary>
            {text(
              "Where is my request saved?",
              "작성한 요청은 어디에 저장되나요?",
            )}
          </summary>
          <p>
            {text(
              "Drafts stay in this browser on this device. Other employees cannot see them here. Clearing browser data removes them, so download a copy for anything you need to keep.",
              "초안은 현재 기기의 이 브라우저에만 저장됩니다. 다른 임직원에게는 표시되지 않습니다. 브라우저 데이터를 삭제하면 초안도 지워지므로 보관할 내용은 다운로드해주세요.",
            )}
          </p>
        </details>
        <details>
          <summary>
            {text(
              "Why does a page say it could not load?",
              "자료나 기록을 불러오지 못하는 이유는 무엇인가요?",
            )}
          </summary>
          <p>
            {text(
              "The live data service is still being connected. It is not a problem with your question. You can prepare and download a request while setup continues.",
              "실시간 자료 서비스를 연결하는 작업이 진행 중입니다. 입력한 질문의 문제가 아닙니다. 연결 전에도 요청을 작성하고 다운로드할 수 있습니다.",
            )}
          </p>
        </details>
        <details>
          <summary>
            {text(
              "Can I upload an internal document?",
              "내부 문서를 업로드할 수 있나요?",
            )}
          </summary>
          <p>
            {text(
              "Document upload is not available in this request form. You can name the procedure or topic to review. Do not paste confidential document contents into a shared or public device.",
              "이 요청 화면에서는 문서 업로드를 지원하지 않습니다. 검토할 절차명이나 주제를 적어주세요. 공용 기기에는 기밀 문서 내용을 붙여넣지 마세요.",
            )}
          </p>
        </details>
        <details>
          <summary>
            {text(
              "Does the AI decide whether we are compliant?",
              "AI가 규정 준수 여부를 판단하나요?",
            )}
          </summary>
          <p>
            {text(
              "No. The intended analysis organizes evidence and questions for a qualified person to review. It does not approve a CAPA, change an SOP, or replace your company’s review process.",
              "아니요. AI는 담당자가 검토할 근거와 질문을 정리하는 역할입니다. CAPA를 승인하거나 SOP를 변경하지 않으며, 회사의 검토 절차를 대신하지 않습니다.",
            )}
          </p>
        </details>
      </section>
      <footer>
        <ShieldCheck size={20} />
        <p>
          {text(
            "You set the question. Agents support the review. Your team owns the decision.",
            "질문은 임직원이, 검토 지원은 에이전트가, 최종 판단은 담당자가 합니다.",
          )}
        </p>
      </footer>
    </article>
  );
}
