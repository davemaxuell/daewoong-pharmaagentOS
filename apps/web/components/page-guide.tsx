"use client";

import { ChevronDown, CircleHelp } from "lucide-react";
import type { ReactNode } from "react";
import { useI18n } from "@/lib/i18n";

type PageGuideProps = {
  title: { ko: string; en: string };
  description: { ko: string; en: string };
  context?: { ko: string; en: string };
  actions?: ReactNode;
  className?: string;
  includePageHeading?: boolean;
};

/**
 * A compact, native disclosure for page-level guidance.
 *
 * The visible marketing-style title block stays out of the working surface,
 * while the screen-reader heading preserves a useful document outline and
 * route announcement fallback.
 */
export function PageGuide({
  title,
  description,
  context,
  actions,
  className = "",
  includePageHeading = true,
}: PageGuideProps) {
  const { locale, text } = useI18n();
  const classes = ["page-guide", "dossier-reveal", className].filter(Boolean).join(" ");

  return (
    <div className={classes}>
      {includePageHeading ? <h1 className="sr-only">{text(title.en, title.ko)}</h1> : null}
      {actions ? <div className="page-guide__actions">{actions}</div> : null}
      <details className="page-guide__disclosure">
        <summary
          className="page-guide__summary"
          aria-label={`${text("About this page", "페이지 안내")}: ${text(title.en, title.ko)}`}
        >
          <span className="page-guide__icon" aria-hidden="true"><CircleHelp size={18} /></span>
          <span className="page-guide__label">
            <strong>
              {text("About this page", "페이지 안내")}
              <span className="sr-only">: {text(title.en, title.ko)}</span>
            </strong>
          </span>
          <ChevronDown className="page-guide__chevron" size={17} aria-hidden="true" />
        </summary>
        <div className="page-guide__panel" lang={locale}>
          {context ? <p className="page-guide__context">{text(context.en, context.ko)}</p> : null}
          <h2>{text(title.en, title.ko)}</h2>
          <p>{text(description.en, description.ko)}</p>
        </div>
      </details>
    </div>
  );
}
