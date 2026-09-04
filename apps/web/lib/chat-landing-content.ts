export type ChatLandingText = Readonly<{
  en: string;
  ko: string;
}>;

export type ChatLandingHeroKind = "prompt" | "fact";

export const CHAT_LANDING_QUESTION_CATEGORIES = [
  "process_validation",
  "data_integrity",
  "quality_unit",
  "investigations_capa",
  "laboratory_controls",
  "stability",
  "aseptic_sterility",
  "supplier_materials",
  "production_controls",
  "documentation_records",
  "regulatory_references",
  "comparisons_trends",
  "inspection_readiness",
] as const;

export type ChatLandingQuestionCategory =
  (typeof CHAT_LANDING_QUESTION_CATEGORIES)[number];

export type ChatLandingHero = Readonly<{
  id: string;
  kind: ChatLandingHeroKind;
  title: ChatLandingText;
  description: ChatLandingText;
}>;

export type ChatLandingQuestion = Readonly<{
  id: string;
  category: ChatLandingQuestionCategory;
  prompt: ChatLandingText;
}>;

export type SelectedChatLandingContent = Readonly<{
  hero: ChatLandingHero;
  questions: readonly ChatLandingQuestion[];
}>;

export const CHAT_LANDING_HEROES = [
  {
    id: "prompt-quality-question",
    kind: "prompt",
    title: {
      en: "Which quality question should we examine today?",
      ko: "오늘은 어떤 품질 질문을 살펴볼까요?",
    },
    description: {
      en: "Trace a concern to the relevant FDA warning-letter evidence.",
      ko: "궁금한 사항을 FDA 경고서한의 관련 근거까지 추적해 보세요.",
    },
  },
  {
    id: "prompt-evidence-needed",
    kind: "prompt",
    title: {
      en: "What evidence would help your review?",
      ko: "검토에 어떤 근거가 필요하신가요?",
    },
    description: {
      en: "Search observations, regulations, firms, dates, or recurring patterns.",
      ko: "지적사항, 규정, 업체, 날짜 또는 반복되는 패턴을 검색해 보세요.",
    },
  },
  {
    id: "prompt-start-source",
    kind: "prompt",
    title: {
      en: "Start with the source. What should we trace?",
      ko: "원문에서 시작해 볼까요? 무엇을 추적할까요?",
    },
    description: {
      en: "Ask a focused question and follow the answer back to its citations.",
      ko: "구체적으로 질문하고 답변의 인용 근거까지 확인해 보세요.",
    },
  },
  {
    id: "prompt-compare-pattern",
    kind: "prompt",
    title: {
      en: "Which warning-letter pattern should we compare?",
      ko: "어떤 경고서한 패턴을 비교해 볼까요?",
    },
    description: {
      en: "Compare source passages across firms, topics, offices, or time periods.",
      ko: "업체, 주제, 발행 부서 또는 기간별 원문을 비교해 보세요.",
    },
  },
  {
    id: "prompt-workflow-concern",
    kind: "prompt",
    title: {
      en: "Is there a workflow concern worth a closer look?",
      ko: "더 자세히 살펴볼 업무 절차가 있나요?",
    },
    description: {
      en: "Use FDA source evidence to frame practical questions for your team.",
      ko: "FDA 원문 근거를 바탕으로 팀에서 검토할 실무 질문을 정리해 보세요.",
    },
  },
  {
    id: "prompt-regulatory-second-look",
    kind: "prompt",
    title: {
      en: "Need a quick regulatory second look?",
      ko: "규제 관점에서 한 번 더 확인해 볼까요?",
    },
    description: {
      en: "Find the relevant warning letters, then verify the cited source passages.",
      ko: "관련 경고서한을 찾고 인용된 원문을 직접 확인해 보세요.",
    },
  },
  {
    id: "prompt-what-changed",
    kind: "prompt",
    title: {
      en: "What changed, and what deserves attention?",
      ko: "무엇이 달라졌고, 어디에 주목해야 할까요?",
    },
    description: {
      en: "Review recent letters and separate source facts from interpretation.",
      ko: "최근 서한을 검토하며 원문 사실과 해석을 구분해 보세요.",
    },
  },
  {
    id: "prompt-evidence-path",
    kind: "prompt",
    title: {
      en: "Turn your question into an evidence path.",
      ko: "궁금한 점을 근거 확인 경로로 바꿔 보세요.",
    },
    description: {
      en: "Search, compare, and open the FDA source behind each cited answer.",
      ko: "검색하고 비교한 뒤, 답변에 인용된 FDA 원문을 열어보세요.",
    },
  },
  {
    id: "prompt-letter-clarity",
    kind: "prompt",
    title: {
      en: "Which letter could clarify your question?",
      ko: "어떤 서한이 궁금한 점을 명확히 해줄까요?",
    },
    description: {
      en: "Find a relevant document or focus the chat on one selected letter.",
      ko: "관련 문서를 찾거나 선택한 서한 한 건에 대화를 집중해 보세요.",
    },
  },
  {
    id: "prompt-one-issue",
    kind: "prompt",
    title: {
      en: "Let’s inspect one quality issue at a time.",
      ko: "품질 이슈를 하나씩 차근차근 살펴볼까요?",
    },
    description: {
      en: "Begin with a process, control, regulation, or observation.",
      ko: "공정, 관리 항목, 규정 또는 지적사항에서 시작해 보세요.",
    },
  },
  {
    id: "prompt-team-verify",
    kind: "prompt",
    title: {
      en: "What should your team verify next?",
      ko: "우리 팀은 다음으로 무엇을 확인해야 할까요?",
    },
    description: {
      en: "Use warning-letter evidence to prepare focused review questions.",
      ko: "경고서한 근거를 활용해 핵심 검토 질문을 준비해 보세요.",
    },
  },
  {
    id: "fact-public-context",
    kind: "fact",
    title: {
      en: "A warning letter is public—but context still matters.",
      ko: "경고서한은 공개되지만, 맥락까지 함께 봐야 합니다.",
    },
    description: {
      en: "Read the cited passage and the surrounding letter before applying it elsewhere.",
      ko: "다른 업무에 참고하기 전, 인용 문구와 서한 전체 맥락을 함께 확인하세요.",
    },
  },
  {
    id: "fact-citation-context",
    kind: "fact",
    title: {
      en: "The same regulation can appear in very different situations.",
      ko: "같은 규정도 서로 다른 상황에서 언급될 수 있습니다.",
    },
    description: {
      en: "Compare the underlying observations, products, and processes—not only the citation.",
      ko: "규정 번호뿐 아니라 지적사항, 제품 및 공정의 차이도 비교하세요.",
    },
  },
  {
    id: "fact-issued-posted-dates",
    kind: "fact",
    title: {
      en: "Issued and posted dates may tell different parts of the timeline.",
      ko: "발행일과 게시일은 서로 다른 시점을 보여줄 수 있습니다.",
    },
    description: {
      en: "Use the appropriate date when reviewing chronology or recent activity.",
      ko: "경과나 최근 동향을 검토할 때 목적에 맞는 날짜를 사용하세요.",
    },
  },
  {
    id: "fact-evidence-first",
    kind: "fact",
    title: {
      en: "Good comparisons begin with source evidence.",
      ko: "좋은 비교는 원문 근거에서 시작합니다.",
    },
    description: {
      en: "Confirm what FDA wrote before drawing parallels to another workflow.",
      ko: "다른 업무 절차와 비교하기 전에 FDA가 실제로 작성한 내용을 확인하세요.",
    },
  },
  {
    id: "fact-record-lifecycle",
    kind: "fact",
    title: {
      en: "A record’s full lifecycle can matter as much as its final value.",
      ko: "기록은 최종값만큼 전체 생애주기도 중요할 수 있습니다.",
    },
    description: {
      en: "Creation, review, change, retention, and retrieval can all shape the evidence trail.",
      ko: "생성, 검토, 변경, 보존 및 조회 과정이 모두 근거의 흐름을 형성할 수 있습니다.",
    },
  },
] as const satisfies readonly ChatLandingHero[];

export const CHAT_LANDING_QUESTIONS = [
  {
    id: "process-validation-api-controls",
    category: "process_validation",
    prompt: {
      en: "Find source passages about process-validation controls in API warning letters.",
      ko: "API 경고서한에서 공정 밸리데이션 관리와 관련된 원문을 찾아주세요.",
    },
  },
  {
    id: "process-validation-continued-verification",
    category: "process_validation",
    prompt: {
      en: "Compare how warning letters discuss continued process verification.",
      ko: "경고서한에서 지속적 공정 검증을 어떻게 다루는지 비교해 주세요.",
    },
  },
  {
    id: "process-validation-protocol-evidence",
    category: "process_validation",
    prompt: {
      en: "What validation protocol or execution evidence is cited in recent FDA Drug warning letters?",
      ko: "최근 FDA 의약품 경고서한에서 어떤 밸리데이션 계획서 또는 수행 근거가 언급되었나요?",
    },
  },
  {
    id: "process-validation-retrospective",
    category: "process_validation",
    prompt: {
      en: "Find letters that discuss weaknesses in retrospective process validation.",
      ko: "회고적 공정 밸리데이션의 미흡사항을 다룬 서한을 찾아주세요.",
    },
  },
  {
    id: "process-validation-batch-variability",
    category: "process_validation",
    prompt: {
      en: "How does FDA source text connect process validation with batch variability?",
      ko: "FDA 원문은 공정 밸리데이션과 배치 변동성을 어떻게 연결하고 있나요?",
    },
  },
  {
    id: "data-integrity-audit-trails",
    category: "data_integrity",
    prompt: {
      en: "Find warning-letter observations involving electronic records and audit trails.",
      ko: "전자 기록과 감사 추적을 다룬 경고서한 지적사항을 찾아주세요.",
    },
  },
  {
    id: "data-integrity-metadata-review",
    category: "data_integrity",
    prompt: {
      en: "Compare FDA Drug warning-letter source passages about metadata and audit-trail review practices.",
      ko: "메타데이터와 감사 추적 검토 방식에 관한 원문을 비교해 주세요.",
    },
  },
  {
    id: "data-integrity-unofficial-records",
    category: "data_integrity",
    prompt: {
      en: "Which FDA Drug warning letters mention unofficial worksheets or incomplete record retention?",
      ko: "비공식 작업지 또는 불완전한 기록 보존을 언급한 FDA 의약품 경고서한은 무엇인가요?",
    },
  },
  {
    id: "data-integrity-access-controls",
    category: "data_integrity",
    prompt: {
      en: "Find FDA Drug warning-letter source evidence about user access controls or shared credentials.",
      ko: "사용자 접근 통제 또는 계정 공유에 관한 FDA 의약품 경고서한 원문 근거를 찾아주세요.",
    },
  },
  {
    id: "data-integrity-complete-records",
    category: "data_integrity",
    prompt: {
      en: "What recurring FDA Drug warning-letter concerns appear around complete, consistent, and accurate records?",
      ko: "FDA 의약품 경고서한에서 완전하고 일관되며 정확한 기록과 관련해 어떤 우려가 반복되나요?",
    },
  },
  {
    id: "quality-unit-211-22",
    category: "quality_unit",
    prompt: {
      en: "Find source evidence related to 21 CFR 211.22 and Quality Unit oversight.",
      ko: "21 CFR 211.22 및 품질 부서 감독과 관련된 원문 근거를 찾아주세요.",
    },
  },
  {
    id: "quality-unit-authority-resources",
    category: "quality_unit",
    prompt: {
      en: "Which letters discuss Quality Unit authority, responsibilities, or resources?",
      ko: "품질 부서의 권한, 책임 또는 자원을 다룬 서한을 찾아주세요.",
    },
  },
  {
    id: "quality-unit-batch-release",
    category: "quality_unit",
    prompt: {
      en: "Compare observations involving Quality Unit oversight of batch release.",
      ko: "배치 출하에 대한 품질 부서 감독 관련 지적사항을 비교해 주세요.",
    },
  },
  {
    id: "quality-unit-deviation-capa",
    category: "quality_unit",
    prompt: {
      en: "Find passages about Quality Unit review of deviations and CAPA decisions.",
      ko: "일탈 및 CAPA 결정에 대한 품질 부서 검토 관련 원문을 찾아주세요.",
    },
  },
  {
    id: "quality-unit-written-responsibilities",
    category: "quality_unit",
    prompt: {
      en: "How do warning letters describe gaps in written Quality Unit responsibilities?",
      ko: "경고서한은 품질 부서의 문서화된 책임 미흡을 어떻게 설명하나요?",
    },
  },
  {
    id: "investigations-oos-root-cause",
    category: "investigations_capa",
    prompt: {
      en: "Find source passages about OOS investigations and root-cause analysis.",
      ko: "OOS 조사 및 근본 원인 분석에 관한 원문을 찾아주세요.",
    },
  },
  {
    id: "investigations-scope-extension",
    category: "investigations_capa",
    prompt: {
      en: "Which FDA Drug warning letters discuss extending an investigation to other batches or products?",
      ko: "조사를 다른 배치나 제품으로 확대하는 내용을 다룬 FDA 의약품 경고서한은 무엇인가요?",
    },
  },
  {
    id: "investigations-capa-effectiveness",
    category: "investigations_capa",
    prompt: {
      en: "Compare warning-letter evidence about CAPA effectiveness checks.",
      ko: "CAPA 효과 확인에 관한 경고서한 근거를 비교해 주세요.",
    },
  },
  {
    id: "investigations-repeat-observations",
    category: "investigations_capa",
    prompt: {
      en: "Find recurring FDA Drug warning-letter observations that may indicate ineffective remediation.",
      ko: "개선조치의 효과가 충분하지 않을 가능성을 보여주는 반복 지적사항을 찾아주세요.",
    },
  },
  {
    id: "investigations-complaints-returns",
    category: "investigations_capa",
    prompt: {
      en: "How do FDA Drug warning letters include complaints, returns, or related signals in investigation scope?",
      ko: "FDA 의약품 경고서한에서 불만, 반품 또는 관련 신호가 조사 범위에 어떻게 포함되는지 찾아주세요.",
    },
  },
  {
    id: "laboratory-method-suitability",
    category: "laboratory_controls",
    prompt: {
      en: "Find FDA Drug warning-letter observations about analytical method validation or suitability.",
      ko: "시험법 밸리데이션 또는 적합성에 관한 지적사항을 찾아주세요.",
    },
  },
  {
    id: "laboratory-standards-reagents",
    category: "laboratory_controls",
    prompt: {
      en: "Which FDA Drug warning letters discuss reference standards, reagents, or solution controls?",
      ko: "표준품, 시약 또는 용액 관리를 다룬 FDA 의약품 경고서한은 무엇인가요?",
    },
  },
  {
    id: "laboratory-sample-management",
    category: "laboratory_controls",
    prompt: {
      en: "Compare source passages about sample handling and laboratory controls.",
      ko: "검체 취급 및 시험실 관리에 관한 원문을 비교해 주세요.",
    },
  },
  {
    id: "laboratory-invalidated-results",
    category: "laboratory_controls",
    prompt: {
      en: "Find FDA Drug warning-letter evidence concerning invalidated, discarded, or unexplained test results.",
      ko: "무효화, 폐기 또는 설명되지 않은 시험 결과에 관한 FDA 의약품 경고서한 근거를 찾아주세요.",
    },
  },
  {
    id: "laboratory-computerized-systems",
    category: "laboratory_controls",
    prompt: {
      en: "What controls for computerized laboratory systems recur in warning letters?",
      ko: "FDA 의약품 경고서한에서 컴퓨터화 시험실 시스템과 관련해 어떤 관리 항목이 반복되나요?",
    },
  },
  {
    id: "stability-retest-support",
    category: "stability",
    prompt: {
      en: "Find warning-letter evidence about stability or retest-period support.",
      ko: "안정성 또는 재시험 기간 근거를 다룬 경고서한 원문을 찾아주세요.",
    },
  },
  {
    id: "stability-storage-pull-schedule",
    category: "stability",
    prompt: {
      en: "Which FDA Drug warning letters discuss stability storage conditions or pull schedules?",
      ko: "안정성 보관 조건 또는 검체 채취 일정을 다룬 FDA 의약품 경고서한은 무엇인가요?",
    },
  },
  {
    id: "stability-trends-oos",
    category: "stability",
    prompt: {
      en: "Compare FDA Drug warning-letter source passages about stability trends and out-of-specification results.",
      ko: "안정성 추세와 기준일탈 결과에 관한 원문을 비교해 주세요.",
    },
  },
  {
    id: "stability-expiry-assignment",
    category: "stability",
    prompt: {
      en: "Find FDA Drug warning-letter observations concerning expiry-date or retest-date assignments.",
      ko: "유효기간 또는 재시험일 설정에 관한 지적사항을 찾아주세요.",
    },
  },
  {
    id: "stability-ongoing-program",
    category: "stability",
    prompt: {
      en: "How do warning letters describe gaps in ongoing stability programs?",
      ko: "경고서한은 지속적 안정성 프로그램의 미흡사항을 어떻게 설명하나요?",
    },
  },
  {
    id: "aseptic-media-fills-monitoring",
    category: "aseptic_sterility",
    prompt: {
      en: "Find source evidence about media fills and environmental monitoring.",
      ko: "배지충전시험 및 환경 모니터링에 관한 원문 근거를 찾아주세요.",
    },
  },
  {
    id: "aseptic-contamination-control",
    category: "aseptic_sterility",
    prompt: {
      en: "Compare contamination-control observations across sterile-drug warning letters.",
      ko: "무균의약품 경고서한의 오염관리 지적사항을 비교해 주세요.",
    },
  },
  {
    id: "aseptic-gowning-qualification",
    category: "aseptic_sterility",
    prompt: {
      en: "Which letters discuss aseptic practices or gowning qualification?",
      ko: "무균 작업 또는 갱의 적격성평가를 다룬 서한은 무엇인가요?",
    },
  },
  {
    id: "aseptic-sterilization-depyrogenation",
    category: "aseptic_sterility",
    prompt: {
      en: "Find passages about sterilization or depyrogenation process controls.",
      ko: "멸균 또는 발열성물질 제거 공정 관리에 관한 원문을 찾아주세요.",
    },
  },
  {
    id: "aseptic-cleanroom-monitoring",
    category: "aseptic_sterility",
    prompt: {
      en: "What cleanroom monitoring concerns recur in the source corpus?",
      ko: "원문 데이터에서 어떤 청정구역 모니터링 우려가 반복되나요?",
    },
  },
  {
    id: "supplier-incoming-identity",
    category: "supplier_materials",
    prompt: {
      en: "Find FDA Drug warning-letter observations about incoming-component identity testing.",
      ko: "입고 원자재의 확인시험에 관한 지적사항을 찾아주세요.",
    },
  },
  {
    id: "supplier-qualification-reduced-testing",
    category: "supplier_materials",
    prompt: {
      en: "Which letters discuss supplier qualification or reduced testing?",
      ko: "공급업체 적격성평가 또는 시험 생략·축소를 다룬 서한은 무엇인가요?",
    },
  },
  {
    id: "supplier-coa-verification",
    category: "supplier_materials",
    prompt: {
      en: "Compare source evidence about verification of supplier certificates of analysis.",
      ko: "공급업체 시험성적서 검증에 관한 원문 근거를 비교해 주세요.",
    },
  },
  {
    id: "supplier-component-risk",
    category: "supplier_materials",
    prompt: {
      en: "How do warning letters frame risk-based controls for components?",
      ko: "경고서한은 원자재의 위험 기반 관리를 어떻게 설명하나요?",
    },
  },
  {
    id: "supplier-contract-oversight",
    category: "supplier_materials",
    prompt: {
      en: "Find FDA Drug warning-letter passages about oversight of contract manufacturers or laboratories.",
      ko: "위탁 제조업체 또는 시험기관 감독에 관한 FDA 의약품 경고서한 원문을 찾아주세요.",
    },
  },
  {
    id: "production-master-batch-records",
    category: "production_controls",
    prompt: {
      en: "Find observations involving master production and batch records.",
      ko: "제품표준서 및 배치 기록과 관련된 지적사항을 찾아주세요.",
    },
  },
  {
    id: "production-yield-reconciliation",
    category: "production_controls",
    prompt: {
      en: "Which FDA Drug warning letters discuss yield calculation or material reconciliation?",
      ko: "수율 계산 또는 물질 수지 확인을 다룬 FDA 의약품 경고서한은 무엇인가요?",
    },
  },
  {
    id: "production-equipment-cleaning",
    category: "production_controls",
    prompt: {
      en: "Compare FDA Drug warning-letter source passages about equipment cleaning and maintenance.",
      ko: "설비 세척 및 유지관리에 관한 FDA 의약품 경고서한 원문을 비교해 주세요.",
    },
  },
  {
    id: "production-change-control",
    category: "production_controls",
    prompt: {
      en: "Find warning-letter evidence related to manufacturing change control.",
      ko: "제조 변경관리에 관한 경고서한 근거를 찾아주세요.",
    },
  },
  {
    id: "production-in-process-controls",
    category: "production_controls",
    prompt: {
      en: "What in-process control concerns recur across manufacturers in FDA Drug warning letters?",
      ko: "FDA 의약품 경고서한에서 제조업체 전반에 어떤 공정 중 관리 우려가 반복되나요?",
    },
  },
  {
    id: "documentation-contemporaneous",
    category: "documentation_records",
    prompt: {
      en: "Find FDA Drug warning-letter source passages about contemporaneous documentation practices.",
      ko: "동시 기록 원칙과 관련된 FDA 의약품 경고서한 원문을 찾아주세요.",
    },
  },
  {
    id: "documentation-corrections-omissions",
    category: "documentation_records",
    prompt: {
      en: "Which FDA Drug warning letters discuss unexplained corrections, omissions, or overwritten records?",
      ko: "설명되지 않은 수정, 누락 또는 덮어쓴 기록을 다룬 FDA 의약품 경고서한은 무엇인가요?",
    },
  },
  {
    id: "documentation-training-records",
    category: "documentation_records",
    prompt: {
      en: "Compare warning-letter evidence about training documentation.",
      ko: "교육 기록에 관한 경고서한 근거를 비교해 주세요.",
    },
  },
  {
    id: "documentation-retention-retrieval",
    category: "documentation_records",
    prompt: {
      en: "Find FDA Drug warning-letter observations concerning record retention and retrieval.",
      ko: "기록 보존 및 조회에 관한 지적사항을 찾아주세요.",
    },
  },
  {
    id: "documentation-sop-implementation",
    category: "documentation_records",
    prompt: {
      en: "How do FDA Drug warning letters distinguish having an SOP from consistently following it?",
      ko: "FDA 의약품 경고서한에서는 SOP 보유와 일관된 준수를 어떻게 구분하나요?",
    },
  },
  {
    id: "regulation-211-22-quality-control",
    category: "regulatory_references",
    prompt: {
      en: "Show the source context for citations to 21 CFR 211.22.",
      ko: "21 CFR 211.22가 인용된 원문 맥락을 보여주세요.",
    },
  },
  {
    id: "regulation-211-192-investigations",
    category: "regulatory_references",
    prompt: {
      en: "Find warning-letter passages that cite 21 CFR 211.192.",
      ko: "21 CFR 211.192를 인용한 경고서한 원문을 찾아주세요.",
    },
  },
  {
    id: "regulation-211-100-procedures",
    category: "regulatory_references",
    prompt: {
      en: "Compare the observations associated with 21 CFR 211.100.",
      ko: "21 CFR 211.100과 관련된 지적사항을 비교해 주세요.",
    },
  },
  {
    id: "regulation-211-165-release-testing",
    category: "regulatory_references",
    prompt: {
      en: "What source issues appear alongside citations to 21 CFR 211.165?",
      ko: "21 CFR 211.165 인용과 함께 어떤 원문 이슈가 나타나나요?",
    },
  },
  {
    id: "regulation-211-166-stability",
    category: "regulatory_references",
    prompt: {
      en: "Find and compare source passages citing 21 CFR 211.166.",
      ko: "21 CFR 211.166을 인용한 원문을 찾아 비교해 주세요.",
    },
  },
  {
    id: "trends-country-comparison",
    category: "comparisons_trends",
    prompt: {
      en: "Compare recurring warning-letter topics across recipient countries.",
      ko: "수신인 국가별로 반복되는 경고서한 주제를 비교해 주세요.",
    },
  },
  {
    id: "trends-issuing-office",
    category: "comparisons_trends",
    prompt: {
      en: "How do cited topics vary by FDA issuing office?",
      ko: "FDA 발행 부서별로 인용 주제가 어떻게 다른가요?",
    },
  },
  {
    id: "trends-recent-topics",
    category: "comparisons_trends",
    prompt: {
      en: "Which warning-letter topics appear most often in the past 12 months?",
      ko: "최근 12개월 동안 가장 자주 나타난 경고서한 주제는 무엇인가요?",
    },
  },
  {
    id: "trends-api-finished-dose",
    category: "comparisons_trends",
    prompt: {
      en: "Compare FDA Drug warning-letter source themes for API and finished-dosage manufacturers.",
      ko: "API와 완제의약품 제조업체의 원문 주제를 비교해 주세요.",
    },
  },
  {
    id: "trends-theme-over-time",
    category: "comparisons_trends",
    prompt: {
      en: "Trace how process-validation topics appear in FDA Drug warning letters over time.",
      ko: "FDA 의약품 경고서한에서 공정 밸리데이션 주제가 시간에 따라 어떻게 나타나는지 추적해 주세요.",
    },
  },
  {
    id: "readiness-self-check-questions",
    category: "inspection_readiness",
    prompt: {
      en: "Turn recurring FDA warning-letter findings about Quality Unit oversight into neutral self-check questions.",
      ko: "품질 부서 감독에 관한 반복적인 FDA 경고서한 지적사항을 객관적인 자체점검 질문으로 바꿔주세요.",
    },
  },
  {
    id: "readiness-evidence-package",
    category: "inspection_readiness",
    prompt: {
      en: "Based on FDA warning-letter evidence, which records are relevant when reviewing OOS investigation controls?",
      ko: "FDA 경고서한 근거를 바탕으로 OOS 조사 관리를 검토할 때 어떤 기록이 관련되나요?",
    },
  },
  {
    id: "readiness-workflow-comparison",
    category: "inspection_readiness",
    prompt: {
      en: "Create a source-backed checklist for comparing FDA warning-letter CAPA observations with an internal workflow, without assuming a gap.",
      ko: "미흡사항을 단정하지 않고 FDA 경고서한의 CAPA 지적사항과 내부 업무 절차를 비교할 원문 근거 기반 점검표를 만들어 주세요.",
    },
  },
  {
    id: "readiness-prioritize-review",
    category: "inspection_readiness",
    prompt: {
      en: "Which source-backed questions should we prioritize when reviewing data-integrity controls in FDA warning letters?",
      ko: "FDA 경고서한의 데이터 무결성 관리를 검토할 때 어떤 원문 근거 기반 질문을 우선해야 하나요?",
    },
  },
  {
    id: "readiness-fact-inference",
    category: "inspection_readiness",
    prompt: {
      en: "Separate source facts, AI interpretation, and internal-evidence questions for recurring process-validation observations in FDA warning letters.",
      ko: "FDA 경고서한의 반복적인 공정 밸리데이션 지적사항에 대해 원문 사실, AI 해석, 내부 근거가 필요한 질문을 구분해 주세요.",
    },
  },
] as const satisfies readonly ChatLandingQuestion[];

const DEFAULT_SEED = "daewoong-fda-new-chat";
const DEFAULT_QUESTION_COUNT = 4;

function normalizeSeed(seed: string): string {
  const normalized = seed.normalize("NFKC").trim();
  return normalized || DEFAULT_SEED;
}

function hashString(value: string): number {
  let hash = 0x811c9dc5;

  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }

  return hash >>> 0;
}

function compareIds(left: { id: string }, right: { id: string }): number {
  if (left.id === right.id) return 0;
  return left.id < right.id ? -1 : 1;
}

function rankBySeed<T extends { id: string }>(
  items: readonly T[],
  seed: string,
  namespace: string,
): T[] {
  return [...items].sort((left, right) => {
    const leftRank = hashString(`${seed}:${namespace}:${left.id}`);
    const rightRank = hashString(`${seed}:${namespace}:${right.id}`);
    return leftRank === rightRank ? compareIds(left, right) : leftRank - rightRank;
  });
}

function selectHero(seed: string): ChatLandingHero {
  // Seven of ten seed buckets select a prompt; the remaining three select a fact.
  const preferredKind: ChatLandingHeroKind =
    hashString(`${seed}:hero-kind`) % 10 < 7 ? "prompt" : "fact";
  const preferredHeroes = CHAT_LANDING_HEROES.filter(
    (hero) => hero.kind === preferredKind,
  );

  return (
    rankBySeed(preferredHeroes, seed, "hero")[0]
    ?? CHAT_LANDING_HEROES[0]
  );
}

function normalizeQuestionCount(count: number | undefined): number {
  const requested = count === undefined || !Number.isFinite(count)
    ? DEFAULT_QUESTION_COUNT
    : Math.trunc(count);

  return Math.min(Math.max(requested, 0), CHAT_LANDING_QUESTIONS.length);
}

function selectQuestions(seed: string, count: number): ChatLandingQuestion[] {
  if (count === 0) return [];

  const rankedCategories = [...CHAT_LANDING_QUESTION_CATEGORIES]
    .map((category) => ({
      category,
      id: category,
    }))
    .sort((left, right) => {
      const leftRank = hashString(`${seed}:category:${left.id}`);
      const rightRank = hashString(`${seed}:category:${right.id}`);
      return leftRank === rightRank ? compareIds(left, right) : leftRank - rightRank;
    });

  const rankedByCategory = new Map<
    ChatLandingQuestionCategory,
    ChatLandingQuestion[]
  >();

  for (const { category } of rankedCategories) {
    const categoryQuestions = CHAT_LANDING_QUESTIONS.filter(
      (question) => question.category === category,
    );
    rankedByCategory.set(
      category,
      rankBySeed(categoryQuestions, seed, `question:${category}`),
    );
  }

  const selected: ChatLandingQuestion[] = [];
  let categoryOffset = 0;

  while (selected.length < count) {
    let addedInPass = false;

    for (const { category } of rankedCategories) {
      const question = rankedByCategory.get(category)?.[categoryOffset];
      if (!question) continue;

      selected.push(question);
      addedInPass = true;
      if (selected.length === count) break;
    }

    if (!addedInPass) break;
    categoryOffset += 1;
  }

  return selected;
}

/**
 * Selects stable landing copy for a chat instance.
 *
 * Use a persistent chat identifier as the seed. The same seed always returns the
 * same content, so rerenders and locale changes do not unexpectedly reshuffle it.
 */
export function selectChatLandingContent(
  seed: string,
  count = DEFAULT_QUESTION_COUNT,
): SelectedChatLandingContent {
  const normalizedSeed = normalizeSeed(seed);
  const normalizedCount = normalizeQuestionCount(count);

  return {
    hero: selectHero(normalizedSeed),
    questions: selectQuestions(normalizedSeed, normalizedCount),
  };
}
