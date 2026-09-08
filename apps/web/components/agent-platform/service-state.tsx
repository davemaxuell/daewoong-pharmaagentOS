"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, RefreshCw, Unplug } from "lucide-react";
import { useI18n } from "@/lib/i18n";

const surfaces = {
  cases: [
    "Team review records",
    "팀 검토 기록",
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
                "A reviewer needs to handle this step",
                "검토 담당자의 권한이 필요한 단계입니다",
              )
            : text(
                "We couldn’t load these review records",
                "검토 기록을 불러오지 못했어요",
              )}
        </h2>
        <p>
          {restricted
            ? text(
                "You can prepare a request without signing in. Approval and review actions are reserved for authorized staff.",
                "로그인 없이 검토 요청을 준비할 수 있습니다. 승인과 정식 검토는 권한이 있는 담당자가 진행합니다.",
              )
            : text(
                "The review service is currently unavailable. You can still write, save, and download a review draft.",
                "현재 검토 기록 서비스에 연결할 수 없습니다. 검토 초안은 작성하고 저장하거나 다운로드할 수 있습니다.",
              )}
        </p>
        <div className="os-service-state__actions">
          <Link className="button button--primary" href="/requests">
            {text("Prepare a request", "검토 요청 작성하기")}
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
        <p><Link href="/help#availability">{text("See available features and next steps", "이용 가능한 기능과 다음 단계 보기")}</Link></p>
        {requestId ? <details><summary>{text("Support details", "문의 시 참고 정보")}</summary><small>Request ID: {requestId}</small></details> : null}
      </div>
    </section>
  );
}
