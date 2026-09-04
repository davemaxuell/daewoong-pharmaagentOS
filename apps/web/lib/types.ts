export type DataMode = "live" | "seeded";

export type ReviewState =
  | "pending"
  | "auto_approved"
  | "approved"
  | "needs_revision"
  | "rejected";

export type LetterAnalysisState = ReviewState | "not_generated";

export type LifecycleState =
  | "ACTIVE"
  | "NEW"
  | "UPDATED"
  | "RESPONSE_ADDED"
  | "CLOSEOUT_ADDED"
  | "RESTORED";

export type AttentionLevel = "high" | "medium" | "routine";

export type Evidence = {
  anchor: string;
  excerpt: string;
  section: string;
};

export type Finding = {
  id: string;
  label: string;
  title: string;
  finding: string;
  categories: string[];
  processLenses: Array<"Preventive" | "Monitoring" | "Retrospective">;
  regulatoryReferences: string[];
  evidence: Evidence[];
  requestedActions: string[];
  comparisonQuestions: string[];
  attentionLevel: AttentionLevel;
  confidence: number;
  reviewState: ReviewState;
};

export type LifecycleEvent = {
  id: string;
  type: LifecycleState | "FIRST_SEEN" | "SCOPE_VERIFIED" | "AI_APPROVED";
  at: string;
  title: string;
  detail: string;
  version?: string;
};

export type OriginalSection = {
  anchor: string;
  heading: string;
  paragraphs: string[];
  highlighted?: boolean;
};

export type LetterAiArtifactType = "translation" | "findings" | "summary";
export type LetterAiArtifactLanguage = "en" | "ko";

export type TranslatedLetterSection = {
  anchor: string;
  heading: string;
  paragraphs: string[];
};

export type AiLetterFinding = {
  label: string;
  title: string;
  finding: string;
  requestedActions: string[];
  categories: string[];
  attentionLevel: AttentionLevel;
  evidenceAnchors: string[];
};

export type AiAttentionPoint = {
  title: string;
  rationale: string;
  sourceAnchors: string[];
};

export type LetterAiArtifactContent = {
  sections?: TranslatedLetterSection[];
  findings?: AiLetterFinding[];
  executiveSummary?: string;
  attentionPoints?: AiAttentionPoint[];
  comparisonQuestions?: string[];
  disclaimer?: string;
};

export type LetterAiArtifact = {
  id: string;
  documentVersionId: string;
  artifactType: LetterAiArtifactType;
  language: LetterAiArtifactLanguage;
  content: LetterAiArtifactContent;
  provider: string;
  modelId: string;
  promptVersion: string;
  sourceHash: string;
  createdAt: string;
};

export type Letter = {
  id: string;
  marcsCms: string;
  company: string;
  country: string;
  subject: string;
  issueDate: string;
  postedDate: string;
  issuingOffice: string;
  productClasses: string[];
  drugSubtypes: string[];
  categories: string[];
  regulations: string[];
  hasResponse: boolean;
  hasCloseout: boolean;
  reviewState: LetterAnalysisState;
  lifecycleState: LifecycleState;
  scopeStatus: "IN_SCOPE_DRUGS";
  executiveSummary: string;
  sourceUrl: string;
  retrievedAt: string;
  sourceHash: string;
  sourceVersion: string;
  facilityType: string;
  findings: Finding[];
  lifecycle: LifecycleEvent[];
  originalSections: OriginalSection[];
  aiArtifacts: LetterAiArtifact[];
  previewKind?: "source-example" | "illustrative";
};

export type ChangeEvent = {
  id: string;
  letterId: string;
  company: string;
  eventType: LifecycleState;
  occurredAt: string;
  summary: string;
};

export type DashboardMetric = {
  label: string;
  value: string;
  delta: string;
  tone: "ink" | "red" | "green" | "ochre";
  detail: string;
};

export type HealthCheck = {
  name: string;
  status: "healthy" | "attention" | "degraded";
  detail: string;
  checkedAt: string;
};

export type TrendPoint = {
  label: string;
  value: number;
  previous?: number;
};

export type DashboardData = {
  metrics: DashboardMetric[];
  changes: ChangeEvent[];
  categoryTrends: TrendPoint[];
  subtypeDistribution: TrendPoint[];
  regulations: Array<{ citation: string; count: number; change: string }>;
  health: HealthCheck[];
  discovery: {
    lastSuccess: string;
    nextRun: string;
    recordsScanned: number;
    inScope: number;
    exceptions: number;
  };
};

export type RagFilter = {
  dateFrom?: string;
  dateTo?: string;
  postedFrom?: string;
  postedTo?: string;
  category?: string;
  regulation?: string;
  company?: string;
  issuingOffice?: string;
  subtype?: string;
  letterId?: string;
};

export type RagConversationMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ChatModelProfile = "auto" | "fast" | "balanced" | "deep";

export type ChatRetrievalMode = "auto" | "none" | "metadata" | "letter" | "corpus";

export type ChatRetrievalStrategy =
  | "none"
  | "metadata"
  | "letter"
  | "multi_letter"
  | "corpus";

export type RagCitation = {
  id: string;
  letterId: string;
  company: string;
  title: string;
  issueDate: string;
  postedDate: string;
  documentType: string;
  anchor: string;
  excerpt: string;
  sourceUrl: string;
  score: number;
  documentVersionId?: string;
  sourceVersion?: string;
  sourceHash?: string;
};

export type RagAnswer = {
  answer: string;
  interpretationLabel: "source_facts" | "ai_synthesis" | "internal_comparison";
  scopeLabel: "FDA Product: Drugs";
  filtersApplied: RagFilter;
  evidenceSufficiency: "sufficient" | "partial" | "insufficient";
  citations: RagCitation[];
  generatedAt: string;
  requestId: string;
  threadId?: string;
  userMessageId?: string;
  assistantMessageId?: string;
  retrievalStrategy?: ChatRetrievalStrategy;
  routeReason?: string;
  requestedModelProfile?: ChatModelProfile;
  effectiveModelProfile?: Exclude<ChatModelProfile, "auto">;
  effectiveModelId?: string;
  attemptedModelId?: string;
  generationUsed: boolean;
  focusedDocumentVersionId?: string;
};

export type ChatMessage = {
  id: string;
  sequence: number;
  role: "user" | "assistant";
  content: string;
  status: "pending" | "streaming" | "complete" | "error" | "cancelled";
  clientMessageId?: string;
  ragQueryId?: string;
  citations: RagCitation[];
  retrievalStrategy?: ChatRetrievalStrategy;
  routeReason?: string;
  requestedModelProfile?: ChatModelProfile;
  effectiveModelProfile?: Exclude<ChatModelProfile, "auto">;
  effectiveModelId?: string;
  attemptedModelId?: string;
  generationUsed: boolean;
  evidenceSufficiency?: "sufficient" | "partial" | "insufficient";
  interpretationLabel?: RagAnswer["interpretationLabel"];
  filtersApplied?: RagFilter;
  requestLanguage?: "auto" | "en" | "ko";
  requestMaxSources?: number;
  requestRetrievalMode?: ChatRetrievalMode;
  requestModelProfile?: ChatModelProfile;
  focusedDocumentVersionId?: string;
  createdAt: string;
  updatedAt?: string;
};

export type ChatDocumentFocus = {
  warningLetterId: string;
  documentId: string;
  documentVersionId: string;
  sourceChunkId: string;
  sourceMessageId: string;
  selectedAt: string;
};

export type ChatThreadSummary = {
  id: string;
  title: string;
  modelPreference: ChatModelProfile;
  retrievalPreference: ChatRetrievalMode;
  activeLetterIds: string[];
  focus?: ChatDocumentFocus;
  archivedAt?: string;
  lastMessageAt: string;
  createdAt: string;
  updatedAt: string;
};

export type ChatThread = ChatThreadSummary & {
  messages: ChatMessage[];
};

export type ChatThreadPage = {
  items: ChatThreadSummary[];
  hasMore: boolean;
  nextCursor?: string;
  page?: number;
  limit?: number;
  total?: number;
};

export type RagQueryOptions = {
  threadId?: string;
  clientMessageId?: string;
  retrievalMode?: ChatRetrievalMode;
  modelProfile?: ChatModelProfile;
};

export type ReviewItem = {
  id: string;
  summaryId: string;
  summaryRevision: number;
  documentVersionId: string;
  letterId: string;
  company: string;
  marcsCms: string;
  submittedAt: string;
  priority: "high" | "normal";
  trigger: string;
  failedChecks: string[];
  sourceExcerpt: string;
  aiFinding: string;
  sourceAnchor: string;
  categories: string[];
  confidence: number | null;
  highAttention: boolean;
  relatedOpenItems: number;
  state: ReviewState;
};

export type SavedViewCriteria = {
  query?: string;
  subtype?: string;
  category?: string;
  country?: string;
  lifecycle?: "ACTIVE" | "NEW" | "UPDATED" | "RESPONSE_ADDED" | "CLOSEOUT_ADDED" | "RESTORED";
  review?: "auto_approved" | "approved" | "needs_revision" | "rejected";
  document?: "response" | "closeout" | "open";
  postedFrom?: string;
  postedTo?: string;
};

export type SavedViewAlertState =
  | "off"
  | "ready"
  | "delivery_unavailable"
  | "digest_scheduler_unavailable"
  | "preview";

export type SavedView = {
  id: string;
  name: string;
  description: string;
  criteria: SavedViewCriteria;
  filters: string[];
  cadence: "Immediate" | "Daily" | "Weekly" | "Off";
  alertState: SavedViewAlertState;
  resultCount: number;
  lastMatched: string;
  owner: string;
  openUrl: string;
  updatedAt: string;
  isPreview?: boolean;
};

export type AdminData = {
  notification: {
    targetEmail: string;
    enabled: boolean;
    smtpDeliveryEnabled: boolean;
    smtpConfigured: boolean;
    queuedDeliveries: number;
    failedDeliveries: number;
    lastDeliveredAt?: string;
    updatedAt?: string;
  };
  corpus: {
    backfillYears: number;
    activeRetentionYears: number;
  };
  health: HealthCheck[];
  queue: Array<{ name: string; depth: number; oldest: string; status: string }>;
  exceptions: Array<{
    id: string;
    type: string;
    source: string;
    detectedAt: string;
    detail: string;
  }>;
  versions: Array<{ component: string; version: string; activatedAt: string; status: string }>;
  controls: Array<{ control: string; status: string; evidence: string }>;
  lastRestoreTest: string;
  backupAge: string;
};

export type ApiResult<T> = {
  data: T;
  mode: DataMode;
  detail?: string;
};
