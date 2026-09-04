"use client";

import Link from "next/link";
import {
  ArrowRight,
  CalendarDays,
  ChevronDown,
  FileCheck2,
  FilterX,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { LetterBookmarkButton } from "@/components/letter-bookmark-button";
import { PageGuide } from "@/components/page-guide";
import type { DataMode, Letter } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import { formatDate, ModeBadge, ScopeBadge, StatusPill } from "@/components/ui";

type Filters = {
  query: string;
  subtype: string;
  category: string;
  country: string;
  lifecycle: string;
  review: string;
  document: string;
  postedFrom: string;
  postedTo: string;
};

type SortOrder = "posted-desc" | "posted-asc" | "issued-desc" | "company-asc";

export type LetterExplorerInitialState = {
  filters?: Partial<Filters>;
  page?: number;
  pageSize?: number;
  sort?: SortOrder;
};

type PaginationItem = number | `ellipsis-${number}-${number}`;

const pageSizeOptions = [20, 50, 100] as const;
const newLetterWindowDays = 7;

const emptyFilters: Filters = {
  query: "",
  subtype: "",
  category: "",
  country: "",
  lifecycle: "",
  review: "",
  document: "",
  postedFrom: "",
  postedTo: "",
};

function unique(values: string[]) {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
}

function hasMeaningfulReference(reference: string) {
  const normalized = reference.trim();
  return Boolean(normalized && !["-", "–", "—"].includes(normalized));
}

function isNewLetter(date: string, now = new Date()) {
  const [year, month, day] = date.split("-").map(Number);
  if (!year || !month || !day) return false;

  const publishedDay = Date.UTC(year, month - 1, day);
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const ageInDays = (today - publishedDay) / 86_400_000;
  return ageInDays >= 0 && ageInDays <= newLetterWindowDays;
}

function getPaginationItems(currentPage: number, totalPages: number): PaginationItem[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1);

  const visiblePages = [...new Set([1, currentPage - 1, currentPage, currentPage + 1, totalPages])]
    .filter((page) => page >= 1 && page <= totalPages)
    .sort((a, b) => a - b);

  const items: PaginationItem[] = [];
  visiblePages.forEach((page, index) => {
    const previousPage = visiblePages[index - 1];
    if (previousPage && page - previousPage === 2) items.push(previousPage + 1);
    if (previousPage && page - previousPage > 2) items.push(`ellipsis-${previousPage}-${page}`);
    items.push(page);
  });
  return items;
}

const optionLabels: Record<string, { en: string; ko: string }> = {
  NEW: { en: "New", ko: "신규" },
  UPDATED: { en: "Updated", ko: "업데이트됨" },
  RESPONSE_ADDED: { en: "Response added", ko: "답변서 추가" },
  CLOSEOUT_ADDED: { en: "Closeout added", ko: "종결서 추가" },
  RESTORED: { en: "Restored", ko: "복원됨" },
  pending: { en: "Pending", ko: "대기" },
  auto_approved: { en: "Auto approved", ko: "자동 승인" },
  approved: { en: "Approved", ko: "승인" },
  needs_revision: { en: "Needs revision", ko: "수정 필요" },
  rejected: { en: "Rejected", ko: "반려" },
  response: { en: "Response", ko: "답변서" },
  closeout: { en: "Closeout", ko: "종결서" },
  open: { en: "Open lifecycle", ko: "미종결" },
};

function SelectFilter({
  label,
  value,
  values,
  onChange,
  allLabel,
  unavailableLabel,
  formatOption = (option) => option.replaceAll("_", " "),
}: {
  label: string;
  value: string;
  values: string[];
  onChange: (value: string) => void;
  allLabel: string;
  unavailableLabel: string;
  formatOption?: (option: string) => string;
}) {
  const hasOptions = values.length > 1;
  return (
    <label className={`filter-field${hasOptions ? "" : " filter-field--unavailable"}`}>
      <span>{label}</span>
      <div>
        <select value={value} onChange={(event) => onChange(event.target.value)} disabled={!hasOptions}>
          <option value="">{hasOptions ? allLabel : unavailableLabel}</option>
          {values.map((option) => (
            <option value={option} key={option}>
              {formatOption(option)}
            </option>
          ))}
        </select>
        <ChevronDown size={14} aria-hidden="true" />
      </div>
    </label>
  );
}

export function LettersExplorer({
  initialLetters,
  initialSavedLetterIds,
  mode,
  initialState = {},
}: {
  initialLetters: Letter[];
  initialSavedLetterIds: string[];
  mode: DataMode;
  initialState?: LetterExplorerInitialState;
}) {
  const { locale, text } = useI18n();
  const resultsRef = useRef<HTMLDivElement>(null);
  const [filters, setFilters] = useState<Filters>({ ...emptyFilters, ...initialState.filters });
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [pageSize, setPageSize] = useState<(typeof pageSizeOptions)[number]>(
    pageSizeOptions.includes(initialState.pageSize as (typeof pageSizeOptions)[number])
      ? (initialState.pageSize as (typeof pageSizeOptions)[number])
      : 20,
  );
  const [requestedPage, setRequestedPage] = useState(Math.max(1, initialState.page ?? 1));
  const [sortOrder, setSortOrder] = useState<SortOrder>(initialState.sort ?? "posted-desc");

  const options = useMemo(
    () => ({
      subtype: unique(initialLetters.flatMap((letter) => letter.drugSubtypes)),
      category: unique(initialLetters.flatMap((letter) => letter.categories)),
      country: unique(initialLetters.map((letter) => letter.country)),
      lifecycle: unique(initialLetters.map((letter) => letter.lifecycleState)).filter(
        (state) => state !== "ACTIVE",
      ),
      review: unique(initialLetters.map((letter) => letter.reviewState)).filter(
        (state) => !["pending", "not_generated"].includes(state),
      ),
    }),
    [initialLetters],
  );

  const letters = useMemo(() => {
    const query = filters.query.trim().toLocaleLowerCase();
    const filtered = initialLetters.filter((letter) => {
      const haystack = [
        letter.company,
        letter.marcsCms,
        letter.subject,
        letter.issuingOffice,
        ...letter.categories,
        ...letter.regulations,
      ]
        .join(" ")
        .toLocaleLowerCase();
      if (query && !haystack.includes(query)) return false;
      if (filters.subtype && !letter.drugSubtypes.includes(filters.subtype)) return false;
      if (filters.category && !letter.categories.includes(filters.category)) return false;
      if (filters.country && letter.country !== filters.country) return false;
      if (filters.lifecycle && letter.lifecycleState !== filters.lifecycle) return false;
      if (filters.review && letter.reviewState !== filters.review) return false;
      if (filters.document === "response" && !letter.hasResponse) return false;
      if (filters.document === "closeout" && !letter.hasCloseout) return false;
      if (filters.document === "open" && letter.hasCloseout) return false;
      const postedDate = letter.postedDate || letter.issueDate;
      if (filters.postedFrom && postedDate < filters.postedFrom) return false;
      if (filters.postedTo && postedDate > filters.postedTo) return false;
      return true;
    });
    return filtered.sort((left, right) => {
      if (sortOrder === "posted-asc") {
        return (left.postedDate || left.issueDate).localeCompare(right.postedDate || right.issueDate);
      }
      if (sortOrder === "issued-desc") return right.issueDate.localeCompare(left.issueDate);
      if (sortOrder === "company-asc") return left.company.localeCompare(right.company);
      return (right.postedDate || right.issueDate).localeCompare(left.postedDate || left.issueDate);
    });
  }, [filters, initialLetters, sortOrder]);

  const documentOptions = useMemo(() => {
    const values: string[] = [];
    if (initialLetters.some((letter) => letter.hasResponse)) values.push("response");
    if (initialLetters.some((letter) => letter.hasCloseout)) values.push("closeout", "open");
    return values;
  }, [initialLetters]);

  const activeFilterCount = Object.entries(filters).filter(([key, value]) => key !== "query" && value).length;
  const totalPages = Math.max(1, Math.ceil(letters.length / pageSize));
  const currentPage = Math.min(requestedPage, totalPages);
  const pageStart = letters.length ? (currentPage - 1) * pageSize + 1 : 0;
  const pageEnd = Math.min(currentPage * pageSize, letters.length);
  const paginatedLetters = letters.slice(pageStart ? pageStart - 1 : 0, pageEnd);
  const paginationItems = getPaginationItems(currentPage, totalPages);
  const resetFilters = () => {
    setFilters(emptyFilters);
    setRequestedPage(1);
  };
  const setFilter = (key: keyof Filters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setRequestedPage(1);
  };
  const formatOption = (value: string) => {
    const label = optionLabels[value];
    const normalized = value.replaceAll("_", " ");
    return label ? text(label.en, label.ko) : text(normalized, `미분류 값 (${normalized})`);
  };

  useEffect(() => {
    const params = new URLSearchParams();
    const filterParams: Array<[keyof Filters, string]> = [
      ["query", "q"],
      ["subtype", "subtype"],
      ["category", "category"],
      ["country", "country"],
      ["lifecycle", "lifecycle"],
      ["review", "review"],
      ["document", "document"],
      ["postedFrom", "postedFrom"],
      ["postedTo", "postedTo"],
    ];
    filterParams.forEach(([key, parameter]) => {
      if (filters[key]) params.set(parameter, filters[key]);
    });
    if (sortOrder !== "posted-desc") params.set("sort", sortOrder);
    if (pageSize !== 20) params.set("pageSize", String(pageSize));
    if (currentPage > 1) params.set("page", String(currentPage));
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}`;
    if (`${window.location.pathname}${window.location.search}` !== nextUrl) {
      window.history.replaceState(window.history.state, "", nextUrl);
    }
  }, [currentPage, filters, pageSize, sortOrder]);

  const selectPage = (page: number) => {
    setRequestedPage(page);
    window.requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  return (
    <div className="page-stack explorer-page">
      <PageGuide
        className="explorer-page__guide"
        title={{ ko: "의약품 경고서한 탐색기", en: "Drug Letter Explorer" }}
        context={{
          ko: `통제된 원문 아카이브 · 현재 기록 ${initialLetters.length}건`,
          en: `Controlled source archive · ${initialLetters.length} current records`,
        }}
        description={{
          ko: "FDA 정식 의약품 경고서한, 승인된 검토 결과, 정확한 인용 및 수명주기 문서를 검색하는 화면입니다. FDA 공식 원문 필드는 영문으로 표시됩니다.",
          en: "Search canonical FDA Drug warning letters, approved findings, exact citations, and lifecycle documents. Official FDA source fields remain in English.",
        }}
        actions={(
          <ModeBadge mode={mode} />
        )}
      />

      <section className="archive-toolbar dossier-reveal dossier-reveal--delay-1" aria-label={text("Letter filters", "경고서한 필터")}>
        <label className="archive-search">
          <Search size={18} aria-hidden="true" />
          <span className="sr-only">{text("Search archive", "아카이브 검색")}</span>
          <input
            value={filters.query}
            onChange={(event) => setFilter("query", event.target.value)}
            placeholder={text("Company, MARCS-CMS, topic, or exact citation", "회사, MARCS-CMS, 주제 또는 정확한 인용")}
          />
          {filters.query ? (
            <button type="button" aria-label={text("Clear search", "검색어 지우기")} onClick={() => setFilter("query", "")}>
              <X size={15} aria-hidden="true" />
            </button>
          ) : null}
        </label>
        <ScopeBadge />
        <button
          className={`filter-toggle${filtersOpen ? " filter-toggle--open" : ""}`}
          type="button"
          onClick={() => setFiltersOpen((value) => !value)}
          aria-expanded={filtersOpen}
          aria-controls="letter-filter-panel"
        >
          <SlidersHorizontal size={16} aria-hidden="true" /> {text("Filters", "필터")}
          {activeFilterCount ? <span>{activeFilterCount}</span> : null}
        </button>
        <button
          className="button button--secondary archive-toolbar__reset"
          type="button"
          onClick={resetFilters}
          aria-label={text("Reset search and all filters", "검색어와 모든 필터 초기화")}
        >
          <FilterX size={16} aria-hidden="true" /> {text("Reset", "초기화")}
        </button>
      </section>

      <section
        className={`filter-drawer${filtersOpen ? " filter-drawer--open" : ""}`}
        id="letter-filter-panel"
        aria-label={text("Expanded letter filters", "펼쳐진 경고서한 필터")}
        aria-hidden={!filtersOpen}
      >
        {filtersOpen ? (
          <>
            <SelectFilter label={text("Drug subtype", "의약품 하위 유형")} value={filters.subtype} values={options.subtype} onChange={(value) => setFilter("subtype", value)} allLabel={text("All", "전체")} unavailableLabel={text("No alternatives", "비교 항목 없음")} />
            <SelectFilter label={text("Category", "범주")} value={filters.category} values={options.category} onChange={(value) => setFilter("category", value)} allLabel={text("All", "전체")} unavailableLabel={text("No alternatives", "비교 항목 없음")} />
            <SelectFilter label={text("Country", "국가")} value={filters.country} values={options.country} onChange={(value) => setFilter("country", value)} allLabel={text("All", "전체")} unavailableLabel={text("No alternatives", "비교 항목 없음")} />
            <SelectFilter label={text("Lifecycle", "수명주기")} value={filters.lifecycle} values={options.lifecycle} onChange={(value) => setFilter("lifecycle", value)} allLabel={text("All", "전체")} unavailableLabel={text("No alternatives", "비교 항목 없음")} formatOption={formatOption} />
            <SelectFilter label={text("Review state", "검토 상태")} value={filters.review} values={options.review} onChange={(value) => setFilter("review", value)} allLabel={text("All", "전체")} unavailableLabel={text("No alternatives", "비교 항목 없음")} formatOption={formatOption} />
            <SelectFilter label={text("Linked documents", "연결된 문서")} value={filters.document} values={documentOptions} onChange={(value) => setFilter("document", value)} allLabel={text("All", "전체")} unavailableLabel={text("No alternatives", "비교 항목 없음")} formatOption={formatOption} />
            <label className="filter-field filter-field--date"><span>{text("Posted from", "게시 시작일")}</span><div><input type="date" value={filters.postedFrom} max={filters.postedTo || undefined} onChange={(event) => setFilter("postedFrom", event.target.value)} /></div></label>
            <label className="filter-field filter-field--date"><span>{text("Posted to", "게시 종료일")}</span><div><input type="date" value={filters.postedTo} min={filters.postedFrom || undefined} onChange={(event) => setFilter("postedTo", event.target.value)} /></div></label>
          </>
        ) : null}
      </section>

      <div ref={resultsRef} className="archive-meta dossier-reveal dossier-reveal--delay-2" role="status" aria-live="polite">
        <div className="archive-meta__count">
          <span>{text("Search results", "검색 결과")}</span>
          <strong>{letters.length}</strong>
          <small>{text(`of ${initialLetters.length} Drug letters`, `전체 ${initialLetters.length}건 중`)}</small>
        </div>
        <div className="archive-meta__context">
          <label className="archive-page-size">
            <span>{text("Letters per page", "페이지당 경고서한")}</span>
            <select
              value={pageSize}
              onChange={(event) => {
                setPageSize(Number(event.target.value) as (typeof pageSizeOptions)[number]);
                setRequestedPage(1);
              }}
              aria-label={text("Letters per page", "페이지당 경고서한 수")}
            >
              {pageSizeOptions.map((size) => <option value={size} key={size}>{size}</option>)}
            </select>
          </label>
          <span className="archive-page-range">
            {text(
              `Showing ${pageStart}–${pageEnd} of ${letters.length}`,
              `${letters.length}건 중 ${pageStart}–${pageEnd}건 표시`,
            )}
          </span>
          {activeFilterCount ? (
            <span>{text(`${activeFilterCount} filters applied`, `필터 ${activeFilterCount}개 적용`)}</span>
          ) : (
            <span>{text("No additional filters", "추가 필터 없음")}</span>
          )}
          <label className="archive-sort"><CalendarDays size={15} aria-hidden="true" /><span className="sr-only">{text("Sort letters", "경고서한 정렬")}</span><select value={sortOrder} onChange={(event) => { setSortOrder(event.target.value as SortOrder); setRequestedPage(1); }}><option value="posted-desc">{text("Posted · newest", "게시일 · 최신순")}</option><option value="posted-asc">{text("Posted · oldest", "게시일 · 오래된순")}</option><option value="issued-desc">{text("Issued · newest", "발행일 · 최신순")}</option><option value="company-asc">{text("Company · A–Z", "회사명 · 가나다/A–Z")}</option></select></label>
        </div>
      </div>

      {letters.length ? (
        <>
          <section className="archive-ledger dossier-reveal dossier-reveal--delay-2" aria-label={text("Drug warning letters", "의약품 경고서한")}>
            <div className="archive-ledger__head" aria-hidden="true">
              <span>{text("Posted / reference", "게시일 / 참조")}</span>
              <span>{text("Warning letter and drug classification", "경고서한 및 의약품 분류")}</span>
              <span>{text("Status and lifecycle", "상태 및 수명주기")}</span>
              <span>{text("Save / source", "저장 / 원문")}</span>
            </div>
            <ol>
              {paginatedLetters.map((letter) => {
                const primaryDate = letter.postedDate || letter.issueDate;
                const primaryDateLabel = letter.postedDate
                  ? text("Posted", "게시")
                  : text("Issued", "발행");
                return (
              <li className="letter-row" key={letter.id}>
                <div className="letter-row__date">
                  <span>{primaryDateLabel}</span>
                  <time dateTime={primaryDate}>{formatDate(primaryDate, { day: "2-digit", month: "short", year: "numeric" }, locale)}</time>
                  {letter.postedDate && letter.issueDate ? (
                    <span>{text("Issued", "발행")} {formatDate(letter.issueDate, { day: "2-digit", month: "short", year: "numeric" }, locale)}</span>
                  ) : null}
                  {hasMeaningfulReference(letter.marcsCms) ? <code>{letter.marcsCms}</code> : null}
                </div>
                <div className="letter-row__identity">
                  <div className="letter-row__titleline">
                    <Link href={`/drug-letters/${letter.id}`} lang="en">{letter.company}</Link>
                    {isNewLetter(primaryDate) ? (
                      <span className="new-letter-mark" title={text("Posted within the last 7 days", "최근 7일 이내 게시됨")}>
                        NEW
                      </span>
                    ) : null}
                    {letter.previewKind === "illustrative" ? <span className="illustrative-label">{text("Illustrative", "예시")}</span> : null}
                  </div>
                  <p
                    className="letter-field-hint letter-field-hint--subject"
                    lang="en"
                    tabIndex={0}
                    title={text("Warning Letter Subject", "경고서한 주제")}
                    aria-label={`${text("Warning Letter Subject", "경고서한 주제")}: ${letter.subject}`}
                    data-field-label={text("Warning Letter Subject", "경고서한 주제")}
                  >
                    {letter.subject}
                  </p>
                  <small className="letter-row__provenance" lang="en">
                    <span
                      className="letter-field-hint letter-field-hint--office"
                      tabIndex={0}
                      title={text("Issuing Office", "발행 부서")}
                      aria-label={`${text("Issuing Office", "발행 부서")}: ${letter.issuingOffice}`}
                      data-field-label={text("Issuing Office", "발행 부서")}
                    >
                      {letter.issuingOffice}
                    </span>
                    <span aria-hidden="true"> · </span>
                    <span
                      className="letter-field-hint letter-field-hint--country"
                      tabIndex={0}
                      title={text("Recipient Country", "수신자 국가")}
                      aria-label={`${text("Recipient Country", "수신자 국가")}: ${letter.country}`}
                      data-field-label={text("Recipient Country", "수신자 국가")}
                    >
                      {letter.country}
                    </span>
                  </small>
                  <div className="letter-row__categories">
                    {letter.categories.slice(0, 2).map((category) => <span key={category} title={category}>{category}</span>)}
                    {letter.categories.length > 2 ? <span>+{letter.categories.length - 2}</span> : null}
                  </div>
                  {letter.drugSubtypes.length ? (
                    <div className="letter-row__classification-compact">
                      <div className="tag-list">
                        {letter.drugSubtypes.slice(0, 2).map((subtype) => <span key={subtype} title={subtype}>{subtype}</span>)}
                        {letter.drugSubtypes.length > 2 ? <span>+{letter.drugSubtypes.length - 2}</span> : null}
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="letter-row__state">
                  {!["pending", "not_generated"].includes(letter.reviewState)
                    ? <StatusPill state={letter.reviewState} />
                    : null}
                  {letter.lifecycleState !== "ACTIVE" ? <strong>{formatOption(letter.lifecycleState)}</strong> : null}
                  <div className="document-flags">
                    {letter.hasResponse ? <span><FileCheck2 size={13} /> {text("Response", "답변서")}</span> : null}
                    {letter.hasCloseout ? <span><FileCheck2 size={13} /> {text("Closeout", "종결서")}</span> : null}
                  </div>
                </div>
                <div className="letter-row__actions">
                  <LetterBookmarkButton
                    letterId={letter.id}
                    initiallySaved={initialSavedLetterIds.includes(letter.id)}
                    compact
                  />
                  <a
                    className="letter-row__open"
                    href={letter.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={text(`Open ${letter.company} on FDA.gov in a new tab`, `새 탭에서 FDA.gov의 ${letter.company} 경고서한 열기`)}
                    title={text("Open the original FDA warning letter", "FDA 경고서한 원문 열기")}
                  >
                    <ArrowRight size={18} aria-hidden="true" />
                  </a>
                </div>
              </li>
                );
              })}
            </ol>
          </section>
          <nav className="archive-pagination" aria-label={text("Warning letter pages", "경고서한 페이지")}>
            <button
              className="archive-pagination__previous"
              type="button"
              onClick={() => selectPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              aria-label={text("Previous page", "이전 페이지")}
            >
              {text("Previous", "이전")}
            </button>
            <div className="archive-pagination__pages">
              {paginationItems.map((item) => typeof item === "number" ? (
                <button
                  className={`archive-pagination__page${item === currentPage ? " archive-pagination__page--current" : ""}`}
                  type="button"
                  key={item}
                  onClick={() => selectPage(item)}
                  aria-label={text(`Page ${item}`, `${item}페이지`)}
                  aria-current={item === currentPage ? "page" : undefined}
                >
                  {item}
                </button>
              ) : (
                <span className="archive-pagination__ellipsis" aria-hidden="true" key={item}>…</span>
              ))}
            </div>
            <button
              className="archive-pagination__next"
              type="button"
              onClick={() => selectPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              aria-label={text("Next page", "다음 페이지")}
            >
              {text("Next", "다음")}
            </button>
          </nav>
        </>
      ) : (
        <section className="empty-state">
          <Search size={24} aria-hidden="true" />
          <h2>{text("No admitted Drug letters match.", "일치하는 등록 의약품 경고서한이 없습니다.")}</h2>
          <p>{text("Broaden the filters. The Product scope remains fixed to canonical FDA Drugs records.", "필터 범위를 넓혀 보세요. Product 범위는 FDA 정식 Drugs 기록으로 고정됩니다.")}</p>
          <button className="button button--secondary" type="button" onClick={resetFilters}>{text("Clear filters", "필터 지우기")}</button>
        </section>
      )}

      <footer className="archive-footnote">
        <strong>{text("Corpus boundary", "코퍼스 경계")}</strong>
        <p>{text("Biologics, devices, foods, and unverified Product metadata are withheld from this archive and from retrieval.", "바이오의약품, 의료기기, 식품, 검증되지 않은 Product 메타데이터는 이 아카이브와 검색에서 제외됩니다.")}</p>
      </footer>
    </div>
  );
}
