export const reviewTemplates = [
  {
    id: "impact",
    en: "Regulatory impact",
    ko: "규제 영향 검토",
    objective: [
      "Assess the potential impact of an FDA warning letter on our quality processes. Identify source evidence, relevant internal documents, and questions for a human reviewer.",
      "FDA 경고서한이 품질 프로세스에 미칠 수 있는 영향을 검토하세요. 원문 근거, 관련 내부 문서, 사람이 확인할 질문을 정리하세요.",
    ],
  },
  {
    id: "evidence",
    en: "Evidence review",
    ko: "근거 검토",
    objective: [
      "Review an FDA warning letter and prepare a source-linked summary of the findings, uncertainties, and questions requiring further review.",
      "FDA 경고서한을 검토하고 원문에 연결된 지적 사항, 불확실성, 추가 검토 질문을 정리하세요.",
    ],
  },
  {
    id: "process",
    en: "Process comparison",
    ko: "프로세스 비교",
    objective: [
      "Compare the observations in an FDA warning letter with relevant internal procedures. Document potential relationships and evidence gaps without making a compliance determination.",
      "FDA 경고서한의 지적 사항과 관련 내부 절차를 비교하세요. 준수 여부를 단정하지 않고 잠재적 연관성과 근거의 공백을 기록하세요.",
    ],
  },
] as const;

// Display summaries of contracts/agents and regulatory-impact-review@1.0.0.
// These are versioned definitions, never live execution or release telemetry.
export const agentDefinitions = [
  {
    key: "case-orchestrator",
    version: "1.0.0",
    name: ["Case orchestrator", "케이스 오케스트레이터"],
    role: [
      "Turns the review objective into bounded specialist tasks and review checkpoints.",
      "검토 목표를 전문가별 작업과 검토 지점으로 구성합니다.",
    ],
    input: ["Review objective and pinned source", "검토 목표와 고정된 원문"],
    output: ["Versioned case plan", "버전이 지정된 케이스 계획"],
    tools: [
      "Planning only · no workflow-step tools",
      "계획 수립 · 이 단계의 도구 없음",
    ],
  },
  {
    key: "regulatory-evidence-agent",
    version: "1.3.0",
    name: ["Regulatory evidence", "규제 근거 에이전트"],
    role: [
      "Extracts findings and exact citations from the retained FDA source version.",
      "보존된 FDA 원문 버전에서 지적 사항과 정확한 인용을 추출합니다.",
    ],
    input: [
      "Approved plan and FDA source version",
      "승인된 계획과 FDA 원문 버전",
    ],
    output: [
      "Source-linked regulatory findings",
      "원문에 연결된 규제 지적 사항",
    ],
    tools: [
      "Source versions · sections · anchors · comparison",
      "원문 버전 · 섹션 · 인용 위치 · 비교",
    ],
  },
  {
    key: "internal-knowledge-agent",
    version: "1.1.0",
    name: ["Internal knowledge", "내부 지식 에이전트"],
    role: [
      "Retrieves relevant internal assets while respecting document access boundaries.",
      "문서 접근 권한 내에서 관련 내부 자료를 검색합니다.",
    ],
    input: [
      "Validated findings and permitted documents",
      "검증된 지적 사항과 접근 가능한 문서",
    ],
    output: ["Relevant internal document candidates", "관련 내부 문서 후보"],
    tools: [
      "Asset search · document versions · revision history",
      "자료 검색 · 문서 버전 · 개정 이력",
    ],
  },
  {
    key: "impact-analysis-agent",
    version: "1.0.2",
    name: ["Impact analysis", "영향 분석 에이전트"],
    role: [
      "Builds evidence-linked impact hypotheses and questions for a human reviewer.",
      "근거에 연결된 영향 가설과 사람이 검토할 질문을 구성합니다.",
    ],
    input: [
      "Regulatory findings and internal candidates",
      "규제 지적 사항과 내부 자료 후보",
    ],
    output: [
      "Impact hypotheses with evidence gaps",
      "근거의 공백을 명시한 영향 가설",
    ],
    tools: [
      "Internal assets · related assets · anchors",
      "내부 자료 · 관련 자료 · 인용 위치",
    ],
  },
  {
    key: "verification-agent",
    version: "1.2.1",
    name: ["Verification", "검증 에이전트"],
    role: [
      "Checks the review package for unsupported claims and unresolved evidence issues.",
      "검토 자료에서 근거 없는 주장과 해결되지 않은 근거 문제를 확인합니다.",
    ],
    input: [
      "Impact hypotheses and retained evidence",
      "영향 가설과 보존된 근거",
    ],
    output: [
      "Verification report and correction requests",
      "검증 보고서와 수정 요청",
    ],
    tools: [
      "Verification task · no workflow-step tools",
      "검증 작업 · 이 단계의 도구 없음",
    ],
  },
] as const;

export const workflowSteps = [
  {
    id: "generate_plan",
    name: ["Build the plan", "검토 계획 수립"],
    kind: "agent",
    agent: 0,
    output: ["Case plan", "케이스 계획"],
  },
  {
    id: "approve_plan",
    name: ["Approve the plan", "계획 승인"],
    kind: "human",
    agent: null,
    output: [
      "Human approval before specialist work",
      "전문가 작업 전 사람의 승인",
    ],
  },
  {
    id: "extract_findings",
    name: ["Extract source evidence", "원문 근거 추출"],
    kind: "agent",
    agent: 1,
    output: [
      "Regulatory findings with citations",
      "인용이 포함된 규제 지적 사항",
    ],
  },
  {
    id: "validate_findings",
    name: ["Validate citations", "인용 검증"],
    kind: "service",
    agent: null,
    output: ["Source-anchor validation", "원문 인용 위치 검증"],
  },
  {
    id: "retrieve_internal_assets",
    name: ["Find internal context", "내부 맥락 검색"],
    kind: "agent",
    agent: 2,
    output: ["Relevant internal documents", "관련 내부 문서"],
  },
  {
    id: "analyze_impact",
    name: ["Map potential impact", "잠재적 영향 연결"],
    kind: "agent",
    agent: 3,
    output: ["Evidence-linked hypotheses", "근거에 연결된 가설"],
  },
  {
    id: "verify",
    name: ["Verify the findings", "결과 검증"],
    kind: "agent",
    agent: 4,
    output: ["Verification report", "검증 보고서"],
  },
  {
    id: "compose_artifact",
    name: ["Prepare the package", "검토 자료 구성"],
    kind: "service",
    agent: null,
    output: ["Regulatory impact review package", "규제 영향 검토 자료"],
  },
  {
    id: "review_artifact",
    name: ["Human review", "최종 검토"],
    kind: "human",
    agent: null,
    output: ["Recorded reviewer decision", "검토자 판단 기록"],
  },
] as const;

export type LocalReviewDraft = {
  version: 1;
  objective: string;
  template: string;
  updatedAt: string;
};
export const REVIEW_DRAFT_KEY = "pharmaagent-os:review-draft:v1";
export function parseReviewDraft(raw: string | null): LocalReviewDraft | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<LocalReviewDraft>;
    if (
      value.version !== 1 ||
      typeof value.objective !== "string" ||
      !value.objective.trim() ||
      value.objective.length > 3000 ||
      !reviewTemplates.some((item) => item.id === value.template) ||
      typeof value.updatedAt !== "string" ||
      !Number.isFinite(Date.parse(value.updatedAt))
    )
      return null;
    return value as LocalReviewDraft;
  } catch {
    return null;
  }
}
