"use client";

import { Bookmark, LoaderCircle } from "lucide-react";
import { useState, useTransition } from "react";
import { setLetterBookmarkAction } from "@/app/(portal)/saved-views/actions";
import { useI18n } from "@/lib/i18n";

export function LetterBookmarkButton({
  letterId,
  initiallySaved,
  compact = false,
  onChange,
}: {
  letterId: string;
  initiallySaved: boolean;
  compact?: boolean;
  onChange?: (saved: boolean) => void;
}) {
  const { text } = useI18n();
  const [saved, setSaved] = useState(initiallySaved);
  const [error, setError] = useState(false);
  const [pending, startTransition] = useTransition();
  const label = saved ? text("Saved", "저장됨") : text("Save", "저장");

  const toggle = () => {
    if (pending) return;
    const nextSaved = !saved;
    setSaved(nextSaved);
    setError(false);
    startTransition(async () => {
      try {
        await setLetterBookmarkAction(letterId, nextSaved);
        onChange?.(nextSaved);
      } catch {
        setSaved(!nextSaved);
        setError(true);
      }
    });
  };

  return (
    <button
      className={`letter-bookmark-button${compact ? " letter-bookmark-button--compact" : " button button--secondary"}${saved ? " is-saved" : ""}`}
      type="button"
      aria-pressed={saved}
      aria-label={error
        ? text("Bookmark could not be updated. Try again.", "북마크를 변경하지 못했습니다. 다시 시도하세요.")
        : text(`${label} this Drug Letter`, `이 의약품 경고서한 ${label}`)}
      title={error
        ? text("Bookmark could not be updated. Try again.", "북마크를 변경하지 못했습니다. 다시 시도하세요.")
        : label}
      disabled={pending}
      onClick={toggle}
    >
      {pending
        ? <LoaderCircle className="spin" size={compact ? 15 : 16} aria-hidden="true" />
        : <Bookmark size={compact ? 15 : 16} fill={saved ? "currentColor" : "none"} aria-hidden="true" />}
      <span>{label}</span>
    </button>
  );
}
