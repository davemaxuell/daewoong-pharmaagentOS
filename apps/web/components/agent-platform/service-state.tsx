"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, RefreshCw, Unplug } from "lucide-react";
import { useI18n } from "@/lib/i18n";

const surfaces = {
  cases: [
    "Cases & runs",
    "케이스 · 실행",
    "Track a review from its objective through specialist work and the final human decision.",
    "검토 목표부터 전문가 작업, 최종 판단까지 하나의 흐름으로 살펴봅니다.",
  ],
  approvals: [
    "Human review",
    "사람의 검토",
    "Inspect agent plans and review packages at the points where a human decision is required.",
    "사람의 판단이 필요한 지점에서 에이전트 계획과 검토 자료를 확인합니다.",
  ],
  evaluations: [
    "Agent evaluations",
    "에이전트 평가",
    "Inspect evaluation definitions, trial records, and release evidence for each agent version.",
    "에이전트 버전별 평가 정의, 시험 기록, 릴리스 근거를 확인합니다.",
  ],
  operations: [
    "Agent operations",
    "에이전트 운영 현황",
    "Follow execution health, agent inventory, and controls for governed work.",
    "실행 상태, 에이전트 목록, 작업 통제를 함께 살펴봅니다.",
  ],
} as const;

export function ServiceState({
  surface,
  restricted = false,
  requestId,
}: {
  surface: keyof typeof surfaces;
  restricted?: boolean;
  requestId?: string;
}) {
  const { text } = useI18n();
  const router = useRouter();
  const content = surfaces[surface];
  return (
    <section className="os-service-state">
      <header>
        <h1>{text(content[0], content[1])}</h1>
        <p>{text(content[2], content[3])}</p>
      </header>
      <div className="os-service-state__body">
        <Unplug size={30} aria-hidden="true" />
        <h2>
          {restricted
            ? text(
                "This action requires an authorized reviewer or operator",
                "이 작업에는 권한이 있는 검토자 또는 운영자가 필요합니다",
              )
            : text(
                "The live workspace is not available yet",
                "실시간 워크스페이스를 아직 사용할 수 없습니다",
              )}
        </h2>
        <p>
          {restricted
            ? text(
                "Public browsing is available without an account. Governed case actions retain their separate review and execution permissions.",
                "계정 없이 공개 화면을 둘러볼 수 있습니다. 정식 케이스 작업에는 별도의 검토 및 실행 권한이 적용됩니다.",
              )
            : text(
                "Case data and agent execution depend on the connected backend. You can still prepare a browser draft and inspect the specialist workflow while the connection is being completed.",
                "케이스 데이터와 에이전트 실행에는 백엔드 연결이 필요합니다. 연결이 완료되기 전에도 브라우저에서 초안을 준비하고 전문가 워크플로를 살펴볼 수 있습니다.",
              )}
        </p>
        <div className="os-service-state__actions">
          <Link className="button button--primary" href="/dashboard">
            {text("Prepare a review brief", "검토 브리프 준비")}
            <ArrowRight size={16} />
          </Link>
          <button
            type="button"
            className="button button--secondary"
            onClick={() => router.refresh()}
          >
            <RefreshCw size={15} />
            {text("Check again", "다시 확인")}
          </button>
        </div>
        <div className="os-service-state__steps">
          <div>
            <strong>{text("Define the objective", "검토 목표 정의")}</strong>
            <p>
              {text(
                "Capture the question and scope in a local brief.",
                "질문과 범위를 브라우저 초안에 정리합니다.",
              )}
            </p>
          </div>
          <div>
            <strong>{text("Inspect the workflow", "워크플로 확인")}</strong>
            <p>
              {text(
                "Review specialist roles, inputs, and expected outputs.",
                "전문가별 역할, 입력, 예정된 출력을 살펴봅니다.",
              )}
            </p>
          </div>
          <div>
            <strong>{text("Connect the evidence", "근거 연결")}</strong>
            <p>
              {text(
                "Live case work requires retained sources and review authority.",
                "정식 케이스 작업에는 보존된 원문과 검토 권한이 필요합니다.",
              )}
            </p>
          </div>
        </div>
        {requestId ? <small>Request ID: {requestId}</small> : null}
      </div>
    </section>
  );
}
