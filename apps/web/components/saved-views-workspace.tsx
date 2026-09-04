"use client";

import Link from "next/link";
import { ArrowRight, Bookmark } from "lucide-react";
import { useState } from "react";
import { LetterBookmarkButton } from "@/components/letter-bookmark-button";
import { PageGuide } from "@/components/page-guide";
import { formatDate, ModeBadge } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import type { DataMode, Letter } from "@/lib/types";

export type SavedLetterEntry = {
  letter: Letter;
  savedAt: string;
};

export function SavedLettersWorkspace({
  initialEntries,
  mode,
}: {
  initialEntries: SavedLetterEntry[];
  mode: DataMode;
}) {
  const { locale, text } = useI18n();
  const [entries, setEntries] = useState(initialEntries);

  return (
    <div className="page-stack saved-letters-page">
      <PageGuide
        className="saved-letters-page__guide"
        title={{ ko: "저장된 경고서한", en: "Saved Drug Letters" }}
        context={{
          ko: `나중에 다시 검토할 경고서한 ${entries.length}건`,
          en: `${entries.length} letter${entries.length === 1 ? "" : "s"} saved for later review`,
        }}
        description={{
          ko: "저장한 경고서한을 한곳에서 다시 열어 원문, 지적사항, 내부 비교 내용을 확인할 수 있습니다.",
          en: "Return to bookmarked warning letters and continue reviewing the source, findings, or internal comparison.",
        }}
        actions={<ModeBadge mode={mode} />}
      />

      {entries.length ? (
        <section className="saved-letter-collection dossier-reveal dossier-reveal--delay-1">
          <header>
            <div>
              <Bookmark size={18} fill="currentColor" aria-hidden="true" />
              <strong>{text("Saved", "저장됨")}</strong>
            </div>
            <span>{text("Newest saved first", "최근 저장순")}</span>
          </header>
          <ol>
            {entries.map(({ letter, savedAt }) => (
              <li key={letter.id}>
                <div className="saved-letter__date">
                  <span>{text("Posted", "게시")}</span>
                  <time dateTime={letter.postedDate || letter.issueDate}>
                    {formatDate(letter.postedDate || letter.issueDate, {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                    }, locale)}
                  </time>
                  <small>
                    {text("Saved", "저장")} {formatDate(savedAt, {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                    }, locale)}
                  </small>
                </div>
                <div className="saved-letter__identity">
                  <Link href={`/drug-letters/${letter.id}`} lang="en">{letter.company}</Link>
                  <p lang="en">{letter.subject}</p>
                  <div>
                    {letter.marcsCms ? <code>{letter.marcsCms}</code> : null}
                    {letter.categories.slice(0, 2).map((category) => <span key={category}>{category}</span>)}
                  </div>
                </div>
                <div className="saved-letter__actions">
                  <LetterBookmarkButton
                    letterId={letter.id}
                    initiallySaved
                    compact
                    onChange={(saved) => {
                      if (!saved) setEntries((current) => current.filter((entry) => entry.letter.id !== letter.id));
                    }}
                  />
                  <Link
                    className="saved-letter__open"
                    href={`/drug-letters/${letter.id}`}
                    aria-label={text(`Read ${letter.company}`, `${letter.company} 읽기`)}
                  >
                    <ArrowRight size={17} aria-hidden="true" />
                  </Link>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : (
        <section className="saved-letters-empty dossier-reveal dossier-reveal--delay-1">
          <Bookmark size={24} aria-hidden="true" />
          <h2>{text("No saved Drug Letters yet", "아직 저장된 의약품 경고서한이 없습니다")}</h2>
          <p>{text(
            "Choose Save on any Drug Letter. It will appear here automatically.",
            "의약품 경고서한에서 저장을 누르면 이곳에 자동으로 표시됩니다.",
          )}</p>
          <Link className="button button--primary" href="/drug-letters">
            {text("Browse Drug Letters", "의약품 경고서한 보기")}
          </Link>
        </section>
      )}
    </div>
  );
}
