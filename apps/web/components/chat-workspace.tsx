"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowUp,
  Bot,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Copy,
  ExternalLink,
  FileSearch,
  FileText,
  Filter,
  LockKeyhole,
  MessageSquare,
  Pin,
  Plus,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  useTransition,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  cancelChatRequest,
  clearChatDocumentFocus,
  createChatConversation,
  focusChatDocument,
  updateChatPreferences,
} from "@/app/(portal)/ask/actions";
import { useChatHistory } from "@/components/chat-history-context";
import { PageGuide } from "@/components/page-guide";
import { selectChatLandingContent } from "@/lib/chat-landing-content";
import { useI18n } from "@/lib/i18n";
import {
  normalizeRagStreamEvent,
  type RagStreamEvent,
  type RagStreamPhase,
} from "@/lib/rag-contract";
import type {
  DataMode,
  ChatMessage,
  ChatModelProfile,
  ChatRetrievalMode,
  ChatRetrievalStrategy,
  ChatThread,
  ChatThreadSummary,
  Letter,
  RagAnswer,
  RagCitation,
  RagConversationMessage,
  RagFilter,
} from "@/lib/types";
import { formatDate } from "@/components/ui";

type ChatTurn = {
  id: string;
  clientMessageId?: string;
  question: string;
  filters: RagFilter;
  requestLanguage?: "auto" | "en" | "ko";
  requestMaxSources?: number;
  requestRetrievalMode?: ChatRetrievalMode;
  requestModelProfile?: ChatModelProfile;
  contextMessages: number;
  persistedContext?: boolean;
  answer?: RagAnswer;
  mode?: DataMode;
  error?: string;
  cancelled?: boolean;
  persistedPending?: boolean;
  provisionalDraft?: string;
  streamAttempt?: number;
  streamPhase?: RagStreamPhase;
};

class ChatStreamFailure extends Error {
  constructor(
    message: string,
    readonly kind: "server" | "protocol" | "incomplete",
    readonly code?: string,
  ) {
    super(message);
    this.name = "ChatStreamFailure";
  }
}

async function consumeChatStream(
  response: Response,
  filters: RagFilter,
  options: {
    threadId?: string;
    clientMessageId?: string;
    retrievalMode: ChatRetrievalMode;
    modelProfile: ChatModelProfile;
  },
  onEvent: (event: RagStreamEvent) => void,
): Promise<RagAnswer> {
  if (!response.body) {
    throw new ChatStreamFailure("The response did not include a readable stream.", "protocol");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  const processLine = (rawLine: string) => {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (!line.trim()) return undefined;
    let payload: unknown;
    try {
      payload = JSON.parse(line);
    } catch {
      throw new ChatStreamFailure("The service returned malformed NDJSON.", "protocol");
    }
    const event = normalizeRagStreamEvent(payload, filters, options);
    if (!event) {
      throw new ChatStreamFailure("The service returned an unknown stream event.", "protocol");
    }
    onEvent(event);
    if (event.type === "error") {
      throw new ChatStreamFailure(event.message, "server", event.code);
    }
    return event.type === "complete" ? event.data : undefined;
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex >= 0) {
        const completed = processLine(buffer.slice(0, newlineIndex));
        buffer = buffer.slice(newlineIndex + 1);
        if (completed) {
          await reader.cancel();
          return completed;
        }
        newlineIndex = buffer.indexOf("\n");
      }
      if (buffer.length > 4_000_000) {
        throw new ChatStreamFailure("The service returned an oversized stream event.", "protocol");
      }
    }
    buffer += decoder.decode();
    const completed = processLine(buffer);
    if (completed) return completed;
    throw new ChatStreamFailure(
      "The connection ended before a verified answer was received.",
      "incomplete",
    );
  } finally {
    reader.releaseLock();
  }
}

function preserveChatOptionFocus(triggerId: string) {
  const focusIfLost = () => {
    if (document.activeElement === document.body) {
      document.getElementById(triggerId)?.focus();
    }
  };
  const observer = new MutationObserver(() => window.requestAnimationFrame(focusIfLost));
  observer.observe(document.body, { childList: true, subtree: true });
  window.setTimeout(() => {
    observer.disconnect();
    focusIfLost();
  }, 2_500);
}

type FilterOption = {
  value: string;
  count: number;
};

function uniqueOptions(values: string[]): FilterOption[] {
  const counts = new Map<string, number>();
  values.filter(Boolean).forEach((value) => counts.set(value, (counts.get(value) ?? 0) + 1));
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((left, right) => left.value.localeCompare(right.value));
}

function formatDateTime(value: string, locale: "en" | "ko") {
  return formatDate(value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Seoul",
  }, locale);
}

function activeFilterEntries(filters: RagFilter) {
  return Object.entries(filters).filter((entry): entry is [keyof RagFilter, string] => Boolean(entry[1]));
}

function answerFromPersistedMessage(
  message: ChatMessage,
  threadId: string,
  fallbackFilters: RagFilter,
): RagAnswer {
  return {
    answer: message.content,
    interpretationLabel: message.interpretationLabel ?? "ai_synthesis",
    scopeLabel: "FDA Product: Drugs",
    filtersApplied: message.filtersApplied ?? fallbackFilters,
    evidenceSufficiency: message.evidenceSufficiency
      ?? (message.citations.length ? "sufficient" : "partial"),
    citations: message.citations,
    generatedAt: message.createdAt,
    requestId: message.ragQueryId ?? message.id,
    threadId,
    assistantMessageId: message.id,
    retrievalStrategy: message.retrievalStrategy ?? "none",
    routeReason: message.routeReason,
    requestedModelProfile: message.requestedModelProfile ?? "auto",
    effectiveModelProfile: message.effectiveModelProfile,
    effectiveModelId: message.effectiveModelId,
    attemptedModelId: message.attemptedModelId,
    generationUsed: message.generationUsed,
    focusedDocumentVersionId: message.focusedDocumentVersionId,
  };
}

function turnsFromPersistedThread(thread: ChatThread | undefined, fallbackFilters: RagFilter): ChatTurn[] {
  if (!thread) return [];
  const turns: ChatTurn[] = [];
  let activeTurn: ChatTurn | undefined;

  thread.messages.forEach((message) => {
    if (message.role === "user") {
      activeTurn = {
        id: message.id,
        clientMessageId: message.clientMessageId,
        question: message.content,
        filters: message.filtersApplied ?? fallbackFilters,
        requestLanguage: message.requestLanguage,
        requestMaxSources: message.requestMaxSources,
        requestRetrievalMode: message.requestRetrievalMode,
        requestModelProfile: message.requestModelProfile,
        contextMessages: 0,
        persistedContext: true,
      };
      turns.push(activeTurn);
      return;
    }
    if (!activeTurn) return;
    if (message.filtersApplied) activeTurn.filters = message.filtersApplied;
    activeTurn.requestLanguage = message.requestLanguage ?? activeTurn.requestLanguage;
    activeTurn.requestMaxSources = message.requestMaxSources ?? activeTurn.requestMaxSources;
    activeTurn.requestRetrievalMode = message.requestRetrievalMode
      ?? activeTurn.requestRetrievalMode;
    activeTurn.requestModelProfile = message.requestModelProfile ?? activeTurn.requestModelProfile;
    if (message.status === "pending" || message.status === "streaming") {
      activeTurn.persistedPending = true;
      return;
    }
    if (message.status === "error" || message.status === "cancelled") {
      activeTurn.error = message.content;
      activeTurn.cancelled = message.status === "cancelled";
      return;
    }
    activeTurn.answer = answerFromPersistedMessage(message, thread.id, activeTurn.filters);
  });

  return turns;
}

const CITATION_MARKER = /^\[((?:\d+\s*,\s*)*\d+)\]$/;
const INLINE_MARKDOWN = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[(?:\d+\s*,\s*)*\d+\])/g;

function MarkdownInline({
  text,
  citations,
  onSelect,
}: {
  text: string;
  citations: RagCitation[];
  onSelect: (index: number) => void;
}) {
  const { text: localize } = useI18n();
  return text.split(INLINE_MARKDOWN).filter(Boolean).map((part, partIndex) => {
    const citationMatch = part.match(CITATION_MARKER);
    if (citationMatch) {
      const citationIndexes = citationMatch[1]
        .split(",")
        .map((value) => Number(value.trim()) - 1)
        .filter((index) => citations[index]);
      if (!citationIndexes.length) return <span key={`${partIndex}-${part}`}>{part}</span>;
      return (
        <span className="inline-citation-group" key={`${partIndex}-${citationMatch[1]}`}>
          {citationIndexes.map((citationIndex, markerIndex) => {
            const citation = citations[citationIndex];
            return (
              <button
                className="inline-citation"
                type="button"
                key={`${citation.id}-${markerIndex}`}
                aria-label={localize(
                  `Open citation ${citationIndex + 1}: ${citation.company}`,
                  `${citation.company}의 ${citationIndex + 1}번 인용 열기`,
                )}
                onClick={() => onSelect(citationIndex)}
              >
                {citationIndex + 1}
              </button>
            );
          })}
        </span>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${partIndex}-${part.slice(0, 10)}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={`${partIndex}-${part.slice(0, 10)}`}>{part.slice(1, -1)}</code>;
    }
    return <span key={`${partIndex}-${part.slice(0, 10)}`}>{part}</span>;
  });
}

function MarkdownCitationText({
  text,
  citations,
  onSelect,
}: {
  text: string;
  citations: RagCitation[];
  onSelect: (index: number) => void;
}) {
  const lines = text.replaceAll("\r\n", "\n").split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let listItems: Array<{ ordered: boolean; content: string }> = [];

  const inline = (value: string, key: string) => (
    <MarkdownInline key={key} text={value} citations={citations} onSelect={onSelect} />
  );
  const flushParagraph = () => {
    if (!paragraph.length) return;
    const value = paragraph.join("\n").trim();
    if (value) blocks.push(<p key={`paragraph-${blocks.length}`}>{inline(value, `inline-${blocks.length}`)}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (!listItems.length) return;
    const ordered = listItems[0].ordered;
    const List = ordered ? "ol" : "ul";
    blocks.push(
      <List key={`list-${blocks.length}`}>
        {listItems.map((item, index) => (
          <li key={`${index}-${item.content.slice(0, 16)}`}>{inline(item.content, `list-inline-${blocks.length}-${index}`)}</li>
        ))}
      </List>,
    );
    listItems = [];
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trimEnd();
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    const boldHeading = line.match(/^\*\*(.+?)\*\*:?$/);
    const unordered = line.match(/^\s*[-*•]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    const quote = line.match(/^>\s?(.+)$/);
    if (!line.trim()) {
      flushParagraph();
      flushList();
    } else if (heading || boldHeading) {
      flushParagraph();
      flushList();
      const value = heading?.[1] ?? boldHeading?.[1] ?? "";
      blocks.push(<h3 key={`heading-${blocks.length}`}>{inline(value, `heading-inline-${blocks.length}`)}</h3>);
    } else if (unordered || ordered) {
      flushParagraph();
      const isOrdered = Boolean(ordered);
      if (listItems.length && listItems[0].ordered !== isOrdered) flushList();
      listItems.push({ ordered: isOrdered, content: (ordered?.[1] ?? unordered?.[1] ?? "").trim() });
    } else if (quote) {
      flushParagraph();
      flushList();
      blocks.push(<blockquote key={`quote-${blocks.length}`}>{inline(quote[1], `quote-inline-${blocks.length}`)}</blockquote>);
    } else {
      flushList();
      paragraph.push(line);
    }
  });
  flushParagraph();
  flushList();

  return (
    <div className="chat-answer__copy">
      {blocks}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  placeholder,
  options,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  placeholder: string;
  options: FilterOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="chat-filter-field">
      <span>{label}</span>
      <div>
        <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
          <option value="">{placeholder}</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.value} ({option.count})
            </option>
          ))}
        </select>
        <ChevronDown size={15} aria-hidden="true" />
      </div>
    </label>
  );
}

function FilterLabel({ name, value }: { name: keyof RagFilter; value: string }) {
  const { text } = useI18n();
  const labels: Record<keyof RagFilter, ReactNode> = {
    letterId: text("Letter", "경고서한"),
    company: text("Company", "기업"),
    issuingOffice: text("FDA office", "FDA 담당 부서"),
    category: text("Finding", "지적 유형"),
    regulation: text("Citation", "규정 인용"),
    subtype: text("Drug type", "의약품 유형"),
    dateFrom: text("Issued after", "발행 시작일"),
    dateTo: text("Issued before", "발행 종료일"),
    postedFrom: text("Posted after", "게시 시작일"),
    postedTo: text("Posted before", "게시 종료일"),
  };
  return <>{labels[name]}: {value}</>;
}

type ChatOption<Value extends string> = {
  value: Value;
  label: string;
  description: string;
  disabled?: boolean;
};

function ChatOptionMenu<Value extends string>({
  ariaLabel,
  triggerId,
  icon,
  value,
  options,
  onChange,
  disabled = false,
}: {
  ariaLabel: string;
  triggerId: string;
  icon: ReactNode;
  value: Value;
  options: ChatOption<Value>[];
  onChange: (value: Value) => void;
  disabled?: boolean;
}) {
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value));
  const selectedOption = options[selectedIndex] ?? options[0];

  const focusOption = useCallback((index: number) => {
    const next = options[index];
    if (!next || next.disabled) return;
    setActiveIndex(index);
    optionRefs.current[index]?.focus();
  }, [options]);

  const openMenu = useCallback((focusIndex = selectedIndex) => {
    if (disabled) return;
    const resolvedIndex = options[focusIndex]?.disabled
      ? Math.max(0, options.findIndex((option) => !option.disabled))
      : focusIndex;
    setActiveIndex(resolvedIndex);
    setOpen(true);
  }, [disabled, options, selectedIndex]);

  useEffect(() => {
    if (!open || disabled) return undefined;
    optionRefs.current[activeIndex]?.focus();
    return undefined;
  }, [activeIndex, disabled, open]);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnPointerDown);
    return () => document.removeEventListener("pointerdown", closeOnPointerDown);
  }, [open]);

  const moveFocus = (direction: 1 | -1) => {
    const currentIndex = optionRefs.current.findIndex((item) => item === document.activeElement);
    const origin = currentIndex >= 0 ? currentIndex : activeIndex;
    for (let offset = 1; offset <= options.length; offset += 1) {
      const nextIndex = (origin + direction * offset + options.length) % options.length;
      if (!options[nextIndex]?.disabled) {
        focusOption(nextIndex);
        return;
      }
    }
  };

  return (
    <div className="chat-option-menu" data-open={open} ref={rootRef}>
      <button
        ref={triggerRef}
        id={triggerId}
        className="chat-option-menu__trigger"
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (open) moveFocus(event.key === "ArrowDown" ? 1 : -1);
            else openMenu();
          } else if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            if (open) setOpen(false);
            else openMenu();
          } else if (event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
          }
        }}
      >
        {icon}
        <span>{selectedOption?.label}</span>
        <ChevronDown size={13} aria-hidden="true" />
      </button>
      <div
        className="chat-option-menu__popover"
        id={listboxId}
        role="listbox"
        aria-label={ariaLabel}
        aria-hidden={!open}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            moveFocus(event.key === "ArrowDown" ? 1 : -1);
          } else if (event.key === "Home" || event.key === "End") {
            event.preventDefault();
            const indexes = options
              .map((option, index) => (option.disabled ? -1 : index))
              .filter((index) => index >= 0);
            focusOption(event.key === "Home" ? indexes[0] : indexes.at(-1) ?? 0);
          } else if (event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
            triggerRef.current?.focus();
          }
        }}
      >
        {options.map((option, index) => (
          <button
            type="button"
            role="option"
            aria-selected={option.value === value}
            disabled={disabled || option.disabled}
            tabIndex={open && activeIndex === index ? 0 : -1}
            key={option.value}
            ref={(node) => { optionRefs.current[index] = node; }}
            onFocus={() => setActiveIndex(index)}
            onClick={() => {
              onChange(option.value);
              setOpen(false);
              triggerRef.current?.focus();
            }}
          >
            <span>
              <strong>{option.label}</strong>
              <small>{option.description}</small>
            </span>
            {option.value === value ? <Check size={14} aria-hidden="true" /> : null}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatWorkspace({
  letters,
  dataMode = "live",
  initialLetterId = "",
  initialCompany = "",
  initialThread,
  landingSeed = "default",
}: {
  letters: Letter[];
  dataMode?: DataMode;
  initialLetterId?: string;
  initialCompany?: string;
  initialThread?: ChatThread;
  landingSeed?: string;
}) {
  const router = useRouter();
  const { locale, text } = useI18n();
  const {
    setActiveThreadId: setHistoryActiveThreadId,
    upsertThread,
  } = useChatHistory();
  const initialLetter = letters.find((letter) => letter.id === initialLetterId);
  const scopedCompany = initialCompany || initialLetter?.company || "";
  const initialRequiredLetterScope: RagFilter = initialLetterId
    ? { letterId: initialLetterId, company: scopedCompany || undefined }
    : {};
  const [question, setQuestion] = useState(() => initialLetter
    && !initialThread ? text(
        `Summarize the principal FDA findings and requested actions for ${initialLetter.company}.`,
        `${initialLetter.company}에 대한 FDA의 주요 지적 사항과 요청 조치를 요약해 주세요.`,
      )
    : "");
  const [filters, setFilters] = useState<RagFilter>(() =>
    initialLetterId
      ? {}
      : initialCompany
        ? { company: initialCompany }
        : {},
  );
  const [maxSources, setMaxSources] = useState(6);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [activeThreadId, setActiveThreadId] = useState(initialThread?.id);
  const [threadTitle, setThreadTitle] = useState(initialThread?.title ?? "");
  const [activeLetterIds, setActiveLetterIds] = useState<string[]>(() => (
    initialThread?.activeLetterIds.length
      ? initialThread.activeLetterIds
      : initialLetterId ? [initialLetterId] : []
  ));
  const [documentFocus, setDocumentFocus] = useState(initialThread?.focus);
  const [focusError, setFocusError] = useState<string>();
  const [modelProfile, setModelProfile] = useState<ChatModelProfile>(
    initialThread?.modelPreference ?? "auto",
  );
  const [retrievalMode, setRetrievalMode] = useState<ChatRetrievalMode>(() => {
    const preference = initialThread?.retrievalPreference ?? (initialLetterId ? "letter" : "auto");
    return ["auto", "none", "metadata", "letter", "corpus"].includes(preference)
      ? preference
      : "auto";
  });
  const [turns, setTurns] = useState<ChatTurn[]>(() => (
    turnsFromPersistedThread(initialThread, initialRequiredLetterScope)
  ));
  const [selectedCitation, setSelectedCitation] = useState<Record<string, number | undefined>>({});
  const [sourcesOpen, setSourcesOpen] = useState<Record<string, boolean>>({});
  const [copiedTurn, setCopiedTurn] = useState<string>();
  const [activeLandingSeed, setActiveLandingSeed] = useState(landingSeed);
  const [activeRequestTurnId, setActiveRequestTurnId] = useState<string>();
  const [pending, startTransition] = useTransition();
  const [focusPending, startFocusTransition] = useTransition();
  const [preferencesPending, startHistoryTransition] = useTransition();
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const conversationRef = useRef<HTMLDivElement>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const followConversationRef = useRef(true);
  const pendingRouteRef = useRef<string | undefined>(undefined);
  const queryPendingRef = useRef(false);
  const requestControllerRef = useRef<AbortController | undefined>(undefined);
  const requestIdentityRef = useRef<{ threadId?: string; clientMessageId?: string }>({});
  const focusMutationRef = useRef(false);
  const preferenceMutationRef = useRef(false);

  const landingContent = useMemo(
    () => selectChatLandingContent(activeLandingSeed, 4),
    [activeLandingSeed],
  );

  useEffect(() => {
    setHistoryActiveThreadId(activeThreadId);
  }, [activeThreadId, setHistoryActiveThreadId]);

  useEffect(() => {
    if (initialThread) upsertThread(initialThread);
  }, [initialThread, upsertThread]);

  useEffect(() => {
    if (!turns.length || !followConversationRef.current) return undefined;
    const frameId = window.requestAnimationFrame(() => {
      const conversation = conversationRef.current;
      if (!conversation || !followConversationRef.current) return;
      conversation.scrollTop = conversation.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [turns]);

  useEffect(() => {
    if (!turns.some((turn) => turn.persistedPending)) return undefined;
    const intervalId = window.setInterval(() => router.refresh(), 3_000);
    return () => window.clearInterval(intervalId);
  }, [router, turns]);

  const companies = useMemo(() => uniqueOptions(letters.map((letter) => letter.company)), [letters]);
  const offices = useMemo(() => uniqueOptions(letters.map((letter) => letter.issuingOffice)), [letters]);
  const categories = useMemo(() => uniqueOptions(letters.flatMap((letter) => letter.categories)), [letters]);
  const regulations = useMemo(() => uniqueOptions(letters.flatMap((letter) => letter.regulations)), [letters]);
  const subtypes = useMemo(() => uniqueOptions(letters.flatMap((letter) => letter.drugSubtypes)), [letters]);
  const primaryLetterId = documentFocus?.warningLetterId
    ?? (activeLetterIds.length === 1 ? activeLetterIds[0] : "");
  const primaryLetter = letters.find((letter) => letter.id === primaryLetterId);
  const primaryCompany = primaryLetter?.company || "";
  const requiredLetterScope: RagFilter = primaryLetterId
    ? { letterId: primaryLetterId, company: primaryCompany || undefined }
    : {};
  const letterScopeSuspended = Boolean(
    primaryLetterId && ["corpus", "none"].includes(retrievalMode),
  );
  const filtersForCurrentScope = letterScopeSuspended
    ? filters
    : { ...filters, ...requiredLetterScope };
  const activeFilters = activeFilterEntries(filtersForCurrentScope);
  const hasRemovableFilters = activeFilters.some(
    ([key]) => !(
      primaryLetterId
      && !letterScopeSuspended
      && (key === "letterId" || key === "company")
    ),
  );

  const modelProfileLabel = (profile: ChatModelProfile) => ({
    auto: text("Auto", "자동"),
    fast: text("Fast", "빠름"),
    balanced: text("Balanced", "균형"),
    deep: text("Deep analysis", "심층 분석"),
  })[profile];

  const modelOptions: ChatOption<ChatModelProfile>[] = [
    {
      value: "auto",
      label: text("Auto", "자동"),
      description: text("Choose the best model for this question", "질문에 맞는 모델을 자동 선택"),
    },
    {
      value: "fast",
      label: text("Fast", "빠름"),
      description: text("Quick answers for straightforward questions", "간단한 질문에 빠르게 답변"),
    },
    {
      value: "balanced",
      label: text("Balanced", "균형"),
      description: text("Balanced speed and reasoning", "속도와 분석 깊이의 균형"),
    },
    {
      value: "deep",
      label: text("Deep analysis", "심층 분석"),
      description: text("More reasoning for complex comparisons", "복잡한 비교를 더 깊게 분석"),
    },
  ];

  const retrievalOptions: ChatOption<ChatRetrievalMode>[] = [
    {
      value: "auto",
      label: text("Auto scope", "자동 범위"),
      description: text("Choose the right evidence scope per question", "질문별 적합한 근거 범위를 자동 선택"),
    },
    {
      value: "none",
      label: text("Conversation only", "대화만"),
      description: text("Do not search documents", "문서를 검색하지 않음"),
    },
    {
      value: "metadata",
      label: text("Letter metadata", "경고서한 기본 정보"),
      description: text("Dates, companies, offices, and record fields", "날짜, 기업, 담당 부서 등 기록 정보"),
    },
    {
      value: "letter",
      label: activeLetterIds.length > 1
        ? text("Selected letters", "선택 서한")
        : text("Current letter", "현재 서한"),
      description: text("Search only the document selected for this chat", "이 대화에서 선택한 문서만 검색"),
      disabled: !activeLetterIds.length,
    },
    {
      value: "corpus",
      label: text("All letters", "전체 코퍼스"),
      description: text("Search across the authorized Drug corpus", "승인된 의약품 전체 코퍼스 검색"),
    },
  ];

  const retrievalStrategyLabel = (strategy: ChatRetrievalStrategy) => ({
    none: text("Conversation context · no document search", "대화 문맥 사용 · 문서 검색 없음"),
    metadata: text("Letter metadata lookup", "경고서한 메타데이터 조회"),
    letter: text("Current-letter evidence", "현재 경고서한 근거 검색"),
    multi_letter: text("Selected-letter comparison", "선택 경고서한 비교 검색"),
    corpus: text("Authorized corpus search", "승인 코퍼스 검색"),
  })[strategy];

  const streamPhaseLabel = (phase?: RagStreamPhase) => ({
    retrieving: text("Retrieving authorized evidence", "승인된 근거를 검색하는 중"),
    generating: text("Drafting the response", "답변 초안을 작성하는 중"),
    validating: text("Validating answer and citations", "답변과 인용을 검증하는 중"),
  })[phase ?? "retrieving"];

  const newChatHref = (seed: string) => {
    const params = new URLSearchParams();
    if (primaryLetterId) params.set("letter", primaryLetterId);
    if (primaryCompany) params.set("company", primaryCompany);
    params.set("new", seed);
    return `/ask?${params.toString()}`;
  };

  const clearConversation = () => {
    const nextLandingSeed = window.crypto.randomUUID();
    setActiveLandingSeed(nextLandingSeed);
    setTurns([]);
    setQuestion(initialLetter
      ? text(
          `Summarize the principal FDA findings and requested actions for ${initialLetter.company}.`,
          `${initialLetter.company}에 대한 FDA의 주요 지적 사항과 요청 조치를 요약해 주세요.`,
        )
      : "");
    setActiveThreadId(undefined);
    setThreadTitle("");
    setDocumentFocus(undefined);
    setFocusError(undefined);
    setActiveLetterIds(primaryLetterId ? [primaryLetterId] : []);
    setModelProfile("auto");
    setRetrievalMode(primaryLetterId ? "letter" : "auto");
    setFilters(primaryLetterId ? {} : initialCompany ? { company: initialCompany } : {});
    setSelectedCitation({});
    setSourcesOpen({});
    requestControllerRef.current?.abort();
    requestControllerRef.current = undefined;
    requestIdentityRef.current = {};
    setActiveRequestTurnId(undefined);
    setHistoryActiveThreadId(undefined);
    pendingRouteRef.current = undefined;
    followConversationRef.current = true;
    router.push(newChatHref(nextLandingSeed), { scroll: false });
    requestAnimationFrame(() => composerRef.current?.focus());
  };

  const changeModelProfile = (nextProfile: ChatModelProfile) => {
    if (preferenceMutationRef.current || focusMutationRef.current) return;
    if (nextProfile === modelProfile) return;
    const previous = modelProfile;
    setModelProfile(nextProfile);
    if (!activeThreadId) return;
    preferenceMutationRef.current = true;
    preserveChatOptionFocus("chat-model-selector");
    startHistoryTransition(async () => {
      try {
        const updated = await updateChatPreferences(activeThreadId, {
          modelPreference: nextProfile,
        });
        upsertThread(updated);
      } catch {
        setModelProfile(previous);
      } finally {
        preferenceMutationRef.current = false;
      }
    });
  };

  const changeRetrievalMode = (nextMode: ChatRetrievalMode) => {
    if (preferenceMutationRef.current || focusMutationRef.current) return;
    if (nextMode === retrievalMode) return;
    const previous = retrievalMode;
    setRetrievalMode(nextMode);
    if (!activeThreadId) return;
    preferenceMutationRef.current = true;
    preserveChatOptionFocus("chat-scope-selector");
    startHistoryTransition(async () => {
      try {
        const updated = await updateChatPreferences(activeThreadId, {
          retrievalPreference: nextMode,
        });
        setDocumentFocus(updated.focus);
        setActiveLetterIds(updated.activeLetterIds);
        upsertThread(updated);
      } catch {
        setRetrievalMode(previous);
      } finally {
        preferenceMutationRef.current = false;
      }
    });
  };

  const setFilter = (key: keyof RagFilter, value: string) => {
    if (
      primaryLetterId
      && !letterScopeSuspended
      && (key === "letterId" || key === "company")
    ) return;
    setFilters((current) => ({ ...current, [key]: value || undefined }));
  };

  const runQuery = (
    nextQuestion: string,
    filterSnapshot = filters,
    contextTurns = turns,
    retry?: {
      clientMessageId: string;
      turnId: string;
      requestLanguage?: "auto" | "en" | "ko";
      requestMaxSources?: number;
      requestRetrievalMode?: ChatRetrievalMode;
      requestModelProfile?: ChatModelProfile;
    },
  ) => {
    const normalized = nextQuestion.trim();
    if (
      normalized.length < 3
      || pending
      || queryPendingRef.current
      || focusMutationRef.current
      || preferenceMutationRef.current
    ) return;
    queryPendingRef.current = true;
    const requestController = new AbortController();
    requestControllerRef.current = requestController;
    const queryLanguage = retry?.requestLanguage ?? "auto";
    const queryMaxSources = retry?.requestMaxSources ?? maxSources;
    const queryRetrievalMode = retry?.requestRetrievalMode ?? retrievalMode;
    const queryModelProfile = retry?.requestModelProfile ?? modelProfile;
    const effectiveFilters: RagFilter = { ...filterSnapshot };
    if (primaryLetterId && !["corpus", "none"].includes(queryRetrievalMode)) {
      Object.assign(effectiveFilters, requiredLetterScope);
    }

    const conversationHistory: RagConversationMessage[] = activeThreadId
      ? []
      : contextTurns
          .filter((turn) => turn.answer)
          .flatMap((turn) => [
            { role: "user" as const, content: turn.question },
            { role: "assistant" as const, content: turn.answer?.answer ?? "" },
          ])
          .slice(-8);

    const turnId = retry?.turnId ?? crypto.randomUUID();
    const clientMessageId = retry?.clientMessageId ?? crypto.randomUUID();
    requestIdentityRef.current = { threadId: activeThreadId, clientMessageId };
    const turn: ChatTurn = {
      id: turnId,
      clientMessageId,
      question: normalized,
      filters: { ...effectiveFilters },
      requestLanguage: queryLanguage,
      requestMaxSources: queryMaxSources,
      requestRetrievalMode: queryRetrievalMode,
      requestModelProfile: queryModelProfile,
      contextMessages: conversationHistory.length,
      persistedContext: Boolean(activeThreadId),
    };
    followConversationRef.current = true;
    setTurns((current) => retry
      ? current.map((item) => (item.id === retry.turnId ? turn : item))
      : [...current, turn]);
    setQuestion("");
    setCopiedTurn(undefined);
    setActiveRequestTurnId(turnId);

    let queryThreadId = activeThreadId;
    startTransition(async () => {
      try {
        if (!queryThreadId) {
          const createdThread = await createChatConversation({
            title: normalized.slice(0, 80),
            modelPreference: queryModelProfile,
            retrievalPreference: queryRetrievalMode,
            activeLetterIds: ["corpus", "none"].includes(queryRetrievalMode)
              ? []
              : activeLetterIds.length
                ? activeLetterIds
                : effectiveFilters.letterId ? [effectiveFilters.letterId] : [],
          });
          queryThreadId = createdThread.id;
          requestIdentityRef.current = { threadId: createdThread.id, clientMessageId };
          pendingRouteRef.current = createdThread.id;
          setActiveThreadId(createdThread.id);
          setThreadTitle(createdThread.title);
          upsertThread(createdThread);
        }

        const response = await fetch("/api/chat/query", {
          method: "POST",
          headers: {
            Accept: "application/x-ndjson",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question: normalized,
            filters: effectiveFilters,
            language: queryLanguage,
            maxSources: queryMaxSources,
            conversationHistory: queryThreadId ? [] : conversationHistory,
            options: {
              threadId: queryThreadId,
              clientMessageId,
              retrievalMode: queryRetrievalMode,
              modelProfile: queryModelProfile,
            },
          }),
          signal: requestController.signal,
        });
        if (!response.ok) {
          let message = `Chat stream could not start (${response.status}).`;
          try {
            const result = await response.json() as { error?: string };
            if (result.error) message = result.error;
          } catch {
            // Keep the bounded status message when an intermediary returns a non-JSON error.
          }
          throw new ChatStreamFailure(message, "server", `http_${response.status}`);
        }
        if (!response.headers.get("content-type")?.toLowerCase().includes("application/x-ndjson")) {
          throw new ChatStreamFailure("The chat endpoint did not return NDJSON.", "protocol");
        }
        const streamOptions = {
          threadId: queryThreadId,
          clientMessageId,
          retrievalMode: queryRetrievalMode,
          modelProfile: queryModelProfile,
        };
        const verifiedAnswer = await consumeChatStream(
          response,
          effectiveFilters,
          streamOptions,
          (event) => {
            if (event.type === "phase") {
              setTurns((current) => current.map((item) => item.id === turnId
                ? { ...item, streamPhase: event.phase }
                : item));
              return;
            }
            if (event.type === "draft_delta") {
              setTurns((current) => current.map((item) => {
                if (item.id !== turnId) return item;
                const sameAttempt = item.streamAttempt === event.attempt;
                return {
                  ...item,
                  provisionalDraft: sameAttempt
                    ? `${item.provisionalDraft ?? ""}${event.text}`
                    : event.text,
                  streamAttempt: event.attempt,
                  streamPhase: "generating",
                };
              }));
              return;
            }
            if (event.type === "draft_reset") {
              setTurns((current) => current.map((item) => item.id === turnId
                ? {
                    ...item,
                    provisionalDraft: undefined,
                    streamAttempt: event.attempt,
                    streamPhase: "generating",
                  }
                : item));
            }
          },
        );
        setTurns((current) => current.map((item) => (
          item.id === turnId
            ? {
                ...item,
                answer: verifiedAnswer,
                mode: "live",
                cancelled: false,
                error: undefined,
                provisionalDraft: undefined,
                streamAttempt: undefined,
                streamPhase: undefined,
              }
            : item
        )));
        setSourcesOpen((current) => ({
          ...current,
          [turnId]: Boolean(verifiedAnswer.citations.length),
        }));
        const returnedThreadId = verifiedAnswer.threadId;
        if (returnedThreadId) {
          const now = verifiedAnswer.generatedAt || new Date().toISOString();
          const nextTitle = threadTitle || normalized.slice(0, 80);
          setActiveThreadId(returnedThreadId);
          setThreadTitle(nextTitle);
          const updatedThread: ChatThreadSummary = {
            id: returnedThreadId,
            title: nextTitle,
            modelPreference: queryModelProfile,
            retrievalPreference: queryRetrievalMode,
            activeLetterIds: ["corpus", "none"].includes(queryRetrievalMode)
              ? []
              : activeLetterIds,
            focus: ["corpus", "none"].includes(queryRetrievalMode)
              ? undefined
              : documentFocus,
            archivedAt: undefined,
            lastMessageAt: now,
            createdAt: initialThread?.createdAt ?? now,
            updatedAt: now,
          };
          upsertThread(updatedThread);
        }
        if (pendingRouteRef.current && pendingRouteRef.current === verifiedAnswer.threadId) {
          const persistedThreadId = pendingRouteRef.current;
          pendingRouteRef.current = undefined;
          router.replace(`/chat/${persistedThreadId}`, { scroll: false });
        } else if (returnedThreadId) {
          // The backend may resolve or clear active letter scope while answering. Refresh the
          // saved thread so sidebar scope and focus always reflect server-owned state.
          router.refresh();
        }
      } catch (error) {
        const requestWasStopped = requestController.signal.aborted;
        const failureMessage = requestWasStopped
          ? text(
              "Display of this request was stopped. The provisional draft was discarded. If the server had already committed a verified answer, it may appear in this conversation after refresh.",
              "요청 표시를 중지했고 검증 전 초안은 폐기했습니다. 서버가 검증된 답변을 이미 저장한 경우 새로고침 후 이 대화에 표시될 수 있습니다.",
            )
          : error instanceof ChatStreamFailure && error.kind === "incomplete"
            ? text(
                "The stream disconnected before the verified completion event. The provisional draft was discarded. Refresh this saved conversation to check whether the server completed it.",
                "검증 완료 이벤트 전에 스트림 연결이 끊어져 검증 전 초안을 폐기했습니다. 서버 처리가 완료되었는지 저장된 대화를 새로고침해 확인하세요.",
              )
            : error instanceof ChatStreamFailure && error.kind === "protocol"
              ? text(
                  "The response stream could not be verified because its format was invalid. No provisional text was accepted as an answer.",
                  "응답 스트림 형식이 올바르지 않아 검증할 수 없습니다. 검증 전 텍스트는 답변으로 채택하지 않았습니다.",
                )
              : error instanceof ChatStreamFailure && error.kind === "server"
                ? text(
                    `The service ended this request before a verified answer was committed${error.code ? ` (${error.code})` : ""}.`,
                    `검증된 답변이 저장되기 전에 서비스가 요청을 종료했습니다${error.code ? ` (${error.code})` : ""}.`,
                  )
                : text(
                    "The stream could not be completed because the connection or service became unavailable. The provisional draft was discarded; try again, then contact an administrator if it persists.",
                    "연결 또는 서비스 문제로 스트림을 완료하지 못해 검증 전 초안을 폐기했습니다. 다시 시도하고 문제가 지속되면 관리자에게 문의하세요.",
                  );
        setTurns((current) => current.map((item) => (
          item.id === turnId
            ? {
                ...item,
                cancelled: requestWasStopped,
                error: failureMessage,
                provisionalDraft: undefined,
                streamAttempt: undefined,
                streamPhase: undefined,
              }
            : item
        )));
        if (
          !requestWasStopped
          && queryThreadId
          && pendingRouteRef.current === queryThreadId
        ) {
          pendingRouteRef.current = undefined;
          router.replace(`/chat/${queryThreadId}`, { scroll: false });
        }
      } finally {
        queryPendingRef.current = false;
        if (requestControllerRef.current === requestController) {
          requestControllerRef.current = undefined;
          requestIdentityRef.current = {};
          setActiveRequestTurnId(undefined);
        }
      }
    });
  };

  const stopActiveRequest = () => {
    const { threadId, clientMessageId } = requestIdentityRef.current;
    requestControllerRef.current?.abort();
    if (threadId && clientMessageId) {
      void cancelChatRequest(threadId, clientMessageId)
        .then(() => {
          pendingRouteRef.current = undefined;
          router.replace(`/chat/${threadId}`, { scroll: false });
          router.refresh();
        })
        .catch(() => {
          // The local request is still stopped. Its error copy truthfully notes that an answer
          // already completed by the server can reappear after the conversation is refreshed.
        });
    }
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      runQuery(question);
    }
  };

  const removeFilter = (key: keyof RagFilter) => {
    if (
      primaryLetterId
      && !letterScopeSuspended
      && (key === "letterId" || key === "company")
    ) return;
    setFilters((current) => ({ ...current, [key]: undefined }));
  };

  const documentTypeLabel = (value: string) => {
    if (value === "warning_letter" || value === "Warning letter") {
      return text("Warning letter", "경고서한");
    }
    if (value === "response" || value === "Response letter") {
      return text("Response", "답변서");
    }
    if (value === "closeout" || value === "Closeout letter") {
      return text("Closeout", "종결서");
    }
    return value.replaceAll("_", " ");
  };

  const selectCitation = (turnId: string, index: number) => {
    setSelectedCitation((current) => ({ ...current, [turnId]: index }));
    setSourcesOpen((current) => ({ ...current, [turnId]: true }));
    requestAnimationFrame(() => document.getElementById(`sources-${turnId}`)?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    }));
  };

  const setCitationAsChatFocus = (turn: ChatTurn, citation: RagCitation) => {
    const assistantMessageId = turn.answer?.assistantMessageId;
    if (
      !activeThreadId
      || !assistantMessageId
      || focusMutationRef.current
      || preferenceMutationRef.current
    ) return;
    setFocusError(undefined);
    focusMutationRef.current = true;
    startFocusTransition(async () => {
      try {
        const updated = await focusChatDocument(
          activeThreadId,
          assistantMessageId,
          citation.id,
        );
        setDocumentFocus(updated.focus);
        setActiveLetterIds(updated.activeLetterIds);
        setRetrievalMode(updated.retrievalPreference);
        setFilters((current) => ({ ...current, letterId: undefined, company: undefined }));
        upsertThread(updated);
        router.refresh();
      } catch {
        setFocusError(text(
          "This document could not be set as the chat focus. Refresh the sources and try again.",
          "이 문서를 대화의 기준으로 설정하지 못했습니다. 출처를 새로고침한 뒤 다시 시도해 주세요.",
        ));
      } finally {
        focusMutationRef.current = false;
      }
    });
  };

  const clearDocumentFocus = () => {
    if (focusMutationRef.current || preferenceMutationRef.current) return;
    if (!activeThreadId) {
      setDocumentFocus(undefined);
      setActiveLetterIds([]);
      setRetrievalMode("auto");
      setFilters((current) => ({ ...current, letterId: undefined, company: undefined }));
      return;
    }
    setFocusError(undefined);
    focusMutationRef.current = true;
    startFocusTransition(async () => {
      try {
        const updated = await clearChatDocumentFocus(activeThreadId);
        setDocumentFocus(undefined);
        setActiveLetterIds(updated.activeLetterIds);
        setRetrievalMode(updated.retrievalPreference);
        upsertThread(updated);
        router.refresh();
      } catch {
        setFocusError(text(
          "The document focus could not be cleared. Please try again.",
          "문서 기준을 해제하지 못했습니다. 다시 시도해 주세요.",
        ));
      } finally {
        focusMutationRef.current = false;
      }
    });
  };

  return (
    <div className={`chat-page${turns.length ? " chat-page--active" : ""}`}>
      <div className="chat-page__surface">
        <PageGuide
          className="chat-page__guide"
          title={{ ko: "FDA 근거 리서치", en: "FDA evidence research" }}
          context={{ ko: "FDA 의약품 인텔리전스", en: "FDA Drug Intelligence" }}
          description={{
            ko: "질문 유형에 따라 대화 문맥, 특정 경고서한 원문 또는 전체 FDA 의약품 코퍼스를 자동으로 선택하고, 근거가 필요한 답변은 공식 FDA 인용으로 확인할 수 있습니다.",
            en: "The assistant automatically chooses conversation context, a specific warning letter, or the FDA Drug corpus and links evidence-based answers to official FDA citations.",
          }}
          actions={(
            <div className="chat-header-actions">
              {activeThreadId && threadTitle ? (
                <span className="chat-active-title" title={threadTitle}>
                  <MessageSquare size={14} aria-hidden="true" />
                  {threadTitle}
                </span>
              ) : null}
              {turns.length ? (
                <button className="chat-new-button" type="button" onClick={clearConversation}>
                  <Plus size={16} aria-hidden="true" />
                  {text("New chat", "새 대화")}
                </button>
              ) : null}
            </div>
          )}
        />

        {dataMode !== "live" ? (
          <div className="chat-service-notice" role="status">
            <CircleAlert size={16} aria-hidden="true" />
            <p><strong>{text("FDA sources are not connected yet.", "FDA 자료를 아직 조회할 수 없어요.")}</strong> {text(
              "Answers about source evidence require the data service. You can prepare and save your review question on the home page.",
              "원문 근거를 확인하는 답변에는 자료 서비스 연결이 필요합니다. 홈에서 검토 질문을 작성하고 저장할 수 있습니다.",
            )}</p>
          </div>
        ) : null}

      <div
        className="chat-page__conversation"
        ref={conversationRef}
        onScroll={(event) => {
          const conversation = event.currentTarget;
          const distanceFromBottom = conversation.scrollHeight
            - conversation.scrollTop
            - conversation.clientHeight;
          followConversationRef.current = distanceFromBottom <= 120;
        }}
      >
        {!turns.length ? (
          <section className="chat-welcome" key={activeLandingSeed}>
            <div
              className={`chat-welcome__mark chat-welcome__mark--${landingContent.hero.kind}`}
              aria-hidden="true"
            >
              {landingContent.hero.kind === "fact"
                ? <Sparkles size={22} />
                : <FileSearch size={22} />}
            </div>
            <h2>{text(
              landingContent.hero.title.en,
              landingContent.hero.title.ko,
            )}</h2>
            <p>{text(
              landingContent.hero.description.en,
              landingContent.hero.description.ko,
            )}</p>
            <div className="chat-suggestions">
              {landingContent.questions.map((prompt) => (
                <button
                  type="button"
                  key={prompt.id}
                  onClick={() => {
                    setQuestion(text(prompt.prompt.en, prompt.prompt.ko));
                    requestAnimationFrame(() => composerRef.current?.focus());
                  }}
                >
                  <Search size={15} aria-hidden="true" />
                  <span>{text(prompt.prompt.en, prompt.prompt.ko)}</span>
                </button>
              ))}
            </div>
            <div className="chat-capabilities" aria-label={text("Available tools", "사용 가능한 도구")}>
              <span><FileSearch size={14} />{text("Search letters", "경고서한 검색")}</span>
              <span><SlidersHorizontal size={14} />{text("Filter evidence", "근거 필터링")}</span>
              <span><FileText size={14} />{text("Trace citations", "인용 추적")}</span>
            </div>
          </section>
        ) : null}

        {turns.map((turn, turnIndex) => {
          const activeSourceIndex = selectedCitation[turn.id] ?? 0;
          const activeSource = turn.answer?.citations[activeSourceIndex];
          const turnFilters = activeFilterEntries(turn.filters);
          return (
            <section className="chat-turn" key={turn.id}>
              <div className="chat-user-message">
                <p>{turn.question}</p>
                {turnFilters.length ? (
                  <div className="chat-turn__filter-summary">
                    <Filter size={13} aria-hidden="true" />
                    <span>{text(`${turnFilters.length} filters applied`, `필터 ${turnFilters.length}개 적용`)}</span>
                  </div>
                ) : null}
              </div>

              {turn.provisionalDraft && !turn.answer && !turn.error ? (
                <article className="chat-unverified-draft">
                  <header role="status">
                    <div>
                      <span className="chat-unverified-draft__mark" aria-hidden="true" />
                      <strong>{text("Unverified draft", "검증 중인 초안")}</strong>
                    </div>
                    <small>{streamPhaseLabel(turn.streamPhase)}</small>
                    {activeRequestTurnId === turn.id ? (
                      <button className="chat-request-stop" type="button" onClick={stopActiveRequest}>
                        <Square size={12} fill="currentColor" aria-hidden="true" />
                        {text("Stop", "중지")}
                      </button>
                    ) : null}
                  </header>
                  <p className="chat-unverified-draft__body">{turn.provisionalDraft}</p>
                  <footer>
                    {text(
                      "Unverified content. Citations, copy, and source controls unlock only after validation.",
                      "검증 전 내용입니다. 인용·복사·출처 기능은 검증 완료 후 활성화됩니다.",
                    )}
                  </footer>
                </article>
              ) : null}

              {!turn.answer && !turn.error && !turn.provisionalDraft ? (
                <div className="chat-tool-run" role="status">
                  <span className="chat-tool-run__spinner" aria-hidden="true" />
                  <div>
                    <strong>{turn.persistedPending ? text(
                      "Waiting for the saved response",
                      "저장된 답변 완료를 기다리는 중",
                    ) : streamPhaseLabel(turn.streamPhase)}</strong>
                    <small>{turn.persistedPending ? text(
                      "This conversation will refresh automatically when processing completes.",
                      "처리가 완료되면 이 대화가 자동으로 새로고침됩니다.",
                    ) : text(
                      "The complete answer appears after its evidence and citations are validated.",
                      "근거와 인용 검증이 끝난 답변만 화면에 표시됩니다.",
                    )}</small>
                  </div>
                  {activeRequestTurnId === turn.id ? (
                    <button className="chat-request-stop" type="button" onClick={stopActiveRequest}>
                      <Square size={12} fill="currentColor" aria-hidden="true" />
                      {text("Stop", "중지")}
                    </button>
                  ) : null}
                </div>
              ) : null}

              {turn.error ? (
                <div className="chat-query-error" role="alert">
                  <CircleAlert size={18} aria-hidden="true" />
                  <div><strong>{turn.cancelled
                    ? text("Request stopped", "요청을 중지했습니다")
                    : text("Answer unavailable", "답변을 생성할 수 없습니다")}</strong><p>{turn.error}</p></div>
                  <button
                    type="button"
                    disabled={pending || focusPending || preferencesPending}
                    onClick={() => runQuery(
                      turn.question,
                      turn.filters,
                      turns.slice(0, turnIndex),
                      turn.clientMessageId
                        ? {
                            clientMessageId: turn.clientMessageId,
                            turnId: turn.id,
                            requestLanguage: turn.requestLanguage,
                            requestMaxSources: turn.requestMaxSources,
                            requestRetrievalMode: turn.requestRetrievalMode,
                            requestModelProfile: turn.requestModelProfile,
                          }
                        : undefined,
                    )}
                  >
                    <RotateCcw size={14} /> {text("Try again", "다시 시도")}
                  </button>
                </div>
              ) : null}

              {turn.answer ? (
                <article className="chat-answer">
                  <span className="sr-only" role="status">{text(
                    `Answer received with ${turn.answer.citations.length} sources.`,
                    `출처 ${turn.answer.citations.length}건과 함께 답변을 받았습니다.`,
                  )}</span>
                  <div className="chat-answer__tool-summary">
                    <span title={turn.answer.routeReason}>
                      <Check size={13} />
                      {retrievalStrategyLabel(turn.answer.retrievalStrategy ?? "corpus")}
                    </span>
                    <span title={turn.answer.effectiveModelId ?? turn.answer.attemptedModelId}>
                      <Bot size={13} />
                      {turn.answer.generationUsed ? (
                        <>
                          {text("Model", "모델")}: {modelProfileLabel(
                            turn.answer.effectiveModelProfile ?? turn.answer.requestedModelProfile ?? "auto",
                          )}
                          {turn.answer.effectiveModelId ? ` · ${turn.answer.effectiveModelId}` : ""}
                        </>
                      ) : turn.answer.attemptedModelId
                        ? turn.answer.retrievalStrategy === "none"
                          ? text(
                              "Model response unavailable · no document search",
                              "모델 응답 사용 불가 · 문서 검색 안 함",
                            )
                          : text(
                              "Source-only fallback · AI output not used",
                              "근거 기반 대체 응답 · AI 출력 미사용",
                            )
                        : text("No model used", "규칙 기반 응답 · 모델 미사용")}
                    </span>
                    {turn.persistedContext ? (
                      <span><Check size={13} />{text(
                        "Saved conversation memory used",
                        "저장된 대화 문맥 사용",
                      )}</span>
                    ) : turn.contextMessages ? (
                      <span><Check size={13} />{text(
                        `${turn.contextMessages} prior messages used as context`,
                        `이전 메시지 ${turn.contextMessages}건을 문맥으로 사용`,
                      )}</span>
                    ) : null}
                    {turn.answer.citations.length ? (
                      <span><LockKeyhole size={13} />{text(
                        `${turn.answer.citations.length} citations linked`,
                        `공식 인용 ${turn.answer.citations.length}건 연결`,
                      )}</span>
                    ) : turn.answer.retrievalStrategy === "none" ? (
                      <span><Check size={13} />{text("No document search needed", "문서 검색 불필요")}</span>
                    ) : (
                      <span><CircleAlert size={13} />{text("No matching sources", "일치하는 출처 없음")}</span>
                    )}
                  </div>

                  <MarkdownCitationText
                    text={turn.answer.answer}
                    citations={turn.answer.citations}
                    onSelect={(index) => selectCitation(turn.id, index)}
                  />

                  {turn.answer.retrievalStrategy !== "none"
                  && turn.answer.evidenceSufficiency !== "sufficient" ? (
                    <div className="chat-evidence-warning">
                      <CircleAlert size={16} />
                      {turn.answer.evidenceSufficiency === "partial"
                        ? text(
                            "The retrieved evidence is limited. Treat the answer as a lead and verify the cited passage before use.",
                            "검색된 근거가 제한적입니다. 답변을 참고 단서로만 사용하고 활용 전에 인용 원문을 확인하세요.",
                          )
                        : text(
                            "The authorized corpus did not contain enough matching evidence. Broaden the filters or revise the query.",
                            "승인된 코퍼스에서 충분한 근거를 찾지 못했습니다. 필터 범위를 넓히거나 질문을 수정하세요.",
                          )}
                    </div>
                  ) : null}

                  {turn.answer.citations.length ? (
                    <div className="chat-sources" id={`sources-${turn.id}`}>
                      <button
                        className="chat-sources__toggle"
                        type="button"
                        aria-expanded={Boolean(sourcesOpen[turn.id])}
                        onClick={() => setSourcesOpen((current) => ({
                          ...current,
                          [turn.id]: !current[turn.id],
                        }))}
                      >
                        <span><FileText size={15} />{text(
                          `Sources (${turn.answer.citations.length})`,
                          `출처 (${turn.answer.citations.length})`,
                        )}</span>
                        {sourcesOpen[turn.id] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                      </button>
                      {sourcesOpen[turn.id] ? (
                        <div className="chat-sources__body">
                          <ol className="chat-source-tabs">
                            {turn.answer.citations.map((citation, index) => (
                              <li key={citation.id}>
                                <button
                                  className={index === activeSourceIndex ? "is-active" : ""}
                                  type="button"
                                  aria-pressed={index === activeSourceIndex}
                                  onClick={() => setSelectedCitation((current) => ({ ...current, [turn.id]: index }))}
                                >
                                  <span>{index + 1}</span>
                                  <div>
                                    <strong>{citation.title || citation.company}</strong>
                                    <small>{citation.company} · {documentTypeLabel(citation.documentType)} · {formatDate(citation.issueDate, undefined, locale)}</small>
                                    <span className="chat-source-tabs__excerpt">{citation.anchor.replaceAll(/[-_/]+/g, " ")} · {citation.excerpt}</span>
                                  </div>
                                </button>
                              </li>
                            ))}
                          </ol>
                          {activeSource ? (
                            <div className="chat-source-preview">
                              <div className="chat-source-preview__meta">
                                <span>{text("Official source excerpt", "공식 원문 발췌")}</span>
                                <code>{activeSource.sourceVersion
                                  ? `${activeSource.sourceVersion}${activeSource.sourceHash ? ` · ${activeSource.sourceHash.slice(0, 8)}` : ""}`
                                  : activeSource.documentVersionId
                                    ? `${text("Captured version", "수집 버전")} · ${activeSource.documentVersionId.slice(0, 8)}`
                                  : text("Current captured version", "현재 수집 버전")}</code>
                              </div>
                              <blockquote lang="en">{activeSource.excerpt}</blockquote>
                              <div className="chat-source-preview__links">
                                <button
                                  className="chat-source-focus"
                                  type="button"
                                  disabled={
                                    focusPending
                                    || preferencesPending
                                    || !turn.answer?.assistantMessageId
                                    || documentFocus?.warningLetterId === activeSource.letterId
                                  }
                                  aria-pressed={documentFocus?.warningLetterId === activeSource.letterId}
                                  onClick={() => setCitationAsChatFocus(turn, activeSource)}
                                >
                                  <Pin size={13} aria-hidden="true" />
                                  {documentFocus?.warningLetterId === activeSource.letterId
                                    ? text("Using as main document", "기준 문서로 사용 중")
                                    : text("Use as main document", "이 문서를 대화 기준으로 사용")}
                                </button>
                                <Link href={`/drug-letters/${activeSource.letterId}`}>
                                  {text("Open dossier", "상세 기록 열기")} <FileText size={13} />
                                </Link>
                                <a href={activeSource.sourceUrl} target="_blank" rel="noreferrer">
                                  {text("View on FDA.gov", "FDA.gov에서 보기")} <ExternalLink size={13} />
                                </a>
                              </div>
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  <details className="chat-provenance">
                    <summary>{text("Answer record", "답변 기록")}</summary>
                    <dl>
                      <div><dt>{text("Generated", "생성 시각")}</dt><dd><time dateTime={turn.answer.generatedAt}>{formatDateTime(turn.answer.generatedAt, locale)}</time></dd></div>
                      <div><dt>{text("Request ID", "요청 ID")}</dt><dd><code>{turn.answer.requestId}</code></dd></div>
                      <div><dt>{text("Requested scope", "요청 범위")}</dt><dd>{turn.requestRetrievalMode ?? "auto"}</dd></div>
                      <div><dt>{text("Applied route", "적용 경로")}</dt><dd>{turn.answer.retrievalStrategy ?? "none"}</dd></div>
                      <div><dt>{text("Language", "응답 언어")}</dt><dd>{turn.requestLanguage ?? "auto"}</dd></div>
                      <div><dt>{text("Maximum sources", "최대 출처")}</dt><dd>{turn.requestMaxSources ?? 6}</dd></div>
                      <div><dt>{text("Requested model", "요청 모델")}</dt><dd>{turn.requestModelProfile ?? "auto"}</dd></div>
                      <div><dt>{text("Effective model", "적용 모델")}</dt><dd>{turn.answer.effectiveModelId ?? text("No model used", "모델 미사용")}</dd></div>
                      {turn.answer.focusedDocumentVersionId ? (
                        <div><dt>{text("Focused document version", "기준 문서 버전")}</dt><dd><code>{turn.answer.focusedDocumentVersionId}</code></dd></div>
                      ) : null}
                      <div className="chat-provenance__filters"><dt>{text("Applied filters", "적용 필터")}</dt><dd>{Object.keys(turn.answer.filtersApplied).length
                        ? JSON.stringify(turn.answer.filtersApplied)
                        : text("None", "없음")}</dd></div>
                    </dl>
                  </details>

                    <footer className="chat-answer__footer">
                      <span>{turn.answer.retrievalStrategy === "none"
                        ? text("Conversational answer · no document search was needed", "대화형 답변 · 문서 검색 없이 생성")
                        : turn.answer.interpretationLabel === "ai_synthesis"
                          ? text("AI-assisted · verify against official FDA sources", "AI 보조 답변 · 공식 FDA 원문 대조 필요")
                          : text("Retrieved source facts · verify in the FDA document", "검색된 원문 사실 · FDA 문서에서 확인 필요")}</span>
                      <div>
                        <button
                          type="button"
                          onClick={async () => {
                            await navigator.clipboard?.writeText(turn.answer?.answer ?? "");
                            setCopiedTurn(turn.id);
                          }}
                        >
                          {copiedTurn === turn.id ? <Check size={14} /> : <Copy size={14} />}
                          {copiedTurn === turn.id ? text("Copied", "복사됨") : text("Copy", "복사")}
                        </button>
                        <button
                          type="button"
                          disabled={pending || focusPending || preferencesPending}
                          onClick={() => runQuery(
                            turn.question,
                            turn.filters,
                            turns.slice(0, turnIndex),
                          )}
                        >
                          <RotateCcw size={14} /> {text("Generate again", "다시 답변")}
                        </button>
                      </div>
                    </footer>
                </article>
              ) : null}
            </section>
          );
        })}
        <div className="chat-scroll-anchor" ref={conversationEndRef} />
      </div>

      <div className="chat-composer-wrap">
        {filtersOpen ? (
          <section className="chat-filter-panel" aria-label={text("Evidence search filters", "증거 검색 필터")}>
            <header>
              <div>
                <span><Filter size={15} />{text("Search filters", "검색 필터")}</span>
                <small>{text("Filters apply to your next question", "다음 질문에 필터가 적용됩니다")}</small>
              </div>
              <button type="button" onClick={() => setFiltersOpen(false)} aria-label={text("Close filters", "필터 닫기")}>
                <X size={17} />
              </button>
            </header>
            <div className="chat-filter-panel__grid">
              <FilterSelect
                label={text("Company", "기업")}
                value={primaryLetterId && !letterScopeSuspended
                  ? primaryCompany
                  : filters.company ?? ""}
                placeholder={text("Available companies", "사용 가능한 기업")}
                options={companies}
                onChange={(value) => setFilter("company", value)}
                disabled={Boolean(primaryLetterId && !letterScopeSuspended)}
              />
              <FilterSelect label={text("Finding category", "지적 유형")} value={filters.category ?? ""} placeholder={text("Available findings", "사용 가능한 지적 유형")} options={categories} onChange={(value) => setFilter("category", value)} />
              <FilterSelect label={text("Regulatory citation", "규정 인용")} value={filters.regulation ?? ""} placeholder={text("Available citations", "사용 가능한 규정 인용")} options={regulations} onChange={(value) => setFilter("regulation", value)} />
              <FilterSelect label={text("Drug subtype", "의약품 유형")} value={filters.subtype ?? ""} placeholder={text("Available drug types", "사용 가능한 의약품 유형")} options={subtypes} onChange={(value) => setFilter("subtype", value)} />
              <FilterSelect label={text("Issuing office", "발행 부서")} value={filters.issuingOffice ?? ""} placeholder={text("Available FDA offices", "사용 가능한 FDA 부서")} options={offices} onChange={(value) => setFilter("issuingOffice", value)} />
              <div className="chat-filter-field chat-filter-field--date">
                <span>{text("Issue date", "발행일")}</span>
                <div className="chat-date-range">
                  <CalendarDays size={15} aria-hidden="true" />
                  <input aria-label={text("Issue date from", "발행 시작일")} type="date" value={filters.dateFrom ?? ""} onChange={(event) => setFilter("dateFrom", event.target.value)} />
                  <span>–</span>
                  <input aria-label={text("Issue date to", "발행 종료일")} type="date" value={filters.dateTo ?? ""} onChange={(event) => setFilter("dateTo", event.target.value)} />
                </div>
              </div>
              <div className="chat-filter-field chat-filter-field--date">
                <span>{text("FDA posted date", "FDA 게시일")}</span>
                <div className="chat-date-range">
                  <CalendarDays size={15} aria-hidden="true" />
                  <input aria-label={text("Posted date from", "게시 시작일")} type="date" value={filters.postedFrom ?? ""} onChange={(event) => setFilter("postedFrom", event.target.value)} />
                  <span>–</span>
                  <input aria-label={text("Posted date to", "게시 종료일")} type="date" value={filters.postedTo ?? ""} onChange={(event) => setFilter("postedTo", event.target.value)} />
                </div>
              </div>
              <div className="chat-filter-field chat-filter-field--sources">
                <span>{text("Maximum sources", "최대 출처 수")}</span>
                <div className="chat-source-count" role="group" aria-label={text("Maximum sources", "최대 출처 수")}>
                  {[4, 6, 10].map((value) => (
                    <button className={maxSources === value ? "is-active" : ""} key={value} type="button" aria-pressed={maxSources === value} onClick={() => setMaxSources(value)}>{value}</button>
                  ))}
                </div>
              </div>
            </div>
            {hasRemovableFilters ? (
              <button className="chat-filter-clear" type="button" onClick={() => setFilters({})}>
                <X size={13} /> {primaryLetterId && !letterScopeSuspended
                  ? text("Clear additional filters", "추가 필터 지우기")
                  : text("Clear all filters", "모든 필터 지우기")}
              </button>
            ) : null}
          </section>
        ) : null}

        {primaryLetterId && !letterScopeSuspended ? (
          <div className="chat-document-focus" role="status">
            <Pin size={14} aria-hidden="true" />
            <span>
              <small>{documentFocus
                ? text("Main document · answers search this captured version", "기준 문서 · 답변은 이 수집 버전에서 검색")
                : text("Current letter scope · answers search only this letter", "현재 서한 범위 · 답변은 이 경고서한에서만 검색")}</small>
              <strong>{primaryCompany || text("Selected FDA warning letter", "선택한 FDA 경고서한")}</strong>
            </span>
            <Link href={`/drug-letters/${primaryLetterId}`}>
              {text("Open", "열기")}
            </Link>
            <button
              type="button"
              disabled={focusPending}
              aria-label={text("Clear main document", "기준 문서 해제")}
              onClick={clearDocumentFocus}
            >
              <X size={13} aria-hidden="true" />
            </button>
          </div>
        ) : null}

        {focusError ? <p className="chat-focus-error" role="alert">{focusError}</p> : null}

        {activeFilters.length ? (
          <div className="chat-filter-chips">
            {activeFilters.map(([key, value]) => (
              <button
                type="button"
                key={key}
                disabled={Boolean(
                  primaryLetterId
                  && !letterScopeSuspended
                  && (key === "letterId" || key === "company"),
                )}
                onClick={() => removeFilter(key)}
                aria-label={primaryLetterId
                  && !letterScopeSuspended
                  && (key === "letterId" || key === "company")
                  ? text(`Locked ${key} context`, `${key} 문맥 고정됨`)
                  : text(`Remove ${key} filter`, `${key} 필터 제거`)}
              >
                <FilterLabel name={key} value={key === "letterId" ? (primaryCompany || value) : value} />
                {primaryLetterId
                && !letterScopeSuspended
                && (key === "letterId" || key === "company")
                  ? <LockKeyhole size={12} />
                  : <X size={12} />}
              </button>
            ))}
          </div>
        ) : null}

        <div className="chat-composer">
          <textarea
            ref={composerRef}
            value={question}
            rows={1}
            maxLength={2000}
            aria-label={text("Ask about FDA warning letters", "FDA 경고서한에 대해 질문하기")}
            placeholder={text("Ask about FDA warning letters…", "FDA 경고서한에 대해 질문하세요…")}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleComposerKeyDown}
          />
          <div className="chat-composer__controls">
            <button
              className={`chat-tool-button${filtersOpen ? " is-active" : ""}`}
              type="button"
              aria-expanded={filtersOpen}
              onClick={() => setFiltersOpen((open) => !open)}
            >
              <SlidersHorizontal size={15} />
              {text("Filters", "필터")}
              {activeFilters.length ? <span>{activeFilters.length}</span> : null}
            </button>
            <ChatOptionMenu
              ariaLabel={text("Choose an AI model", "AI 모델 선택")}
              triggerId="chat-model-selector"
              icon={<Sparkles size={14} aria-hidden="true" />}
              value={modelProfile}
              options={modelOptions}
              onChange={changeModelProfile}
              disabled={focusPending || preferencesPending}
            />
            <ChatOptionMenu
              ariaLabel={text("Choose the evidence scope", "근거 범위 선택")}
              triggerId="chat-scope-selector"
              icon={<FileSearch size={14} aria-hidden="true" />}
              value={retrievalMode}
              options={retrievalOptions}
              onChange={changeRetrievalMode}
              disabled={focusPending || preferencesPending}
            />
            <div className="chat-composer__scope">
              <LockKeyhole size={13} />
              {text("FDA Product: Drugs", "FDA 제품: 의약품")}
            </div>
            {activeRequestTurnId ? (
              <button
                className="chat-send-button chat-send-button--stop"
                type="button"
                aria-label={text("Stop waiting for this answer", "이 답변 요청 중지")}
                onClick={stopActiveRequest}
              >
                <Square size={13} fill="currentColor" aria-hidden="true" />
              </button>
            ) : (
              <button
                className="chat-send-button"
                type="button"
                disabled={
                  pending
                  || focusPending
                  || preferencesPending
                  || question.trim().length < 3
                }
                aria-label={text("Send message", "메시지 보내기")}
                onClick={() => runQuery(question)}
              >
                <ArrowUp size={17} strokeWidth={2.2} />
              </button>
            )}
          </div>
        </div>
        <p className="chat-composer-note">
          {text(
            "AI can make mistakes. Confirm critical details in the cited FDA source. Enter to send · Shift + Enter for a new line.",
            "AI 답변에는 오류가 있을 수 있습니다. 중요 정보는 인용된 FDA 원문에서 확인하세요. Enter 전송 · Shift + Enter 줄바꿈.",
          )}
        </p>
      </div>
      </div>
    </div>
  );
}
