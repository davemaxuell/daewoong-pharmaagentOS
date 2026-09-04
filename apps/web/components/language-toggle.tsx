"use client";

import { Languages } from "lucide-react";
import { useI18n, type Locale } from "@/lib/i18n";

const languageOptions: Array<{ locale: Locale; label: string; name: string }> = [
  { locale: "en", label: "EN", name: "English" },
  { locale: "ko", label: "한국어", name: "한국어" },
];

export function LanguageToggle() {
  const { locale, setLocale, text } = useI18n();

  return (
    <div
      className="language-toggle"
      role="group"
      aria-label={text("Interface language", "인터페이스 언어")}
    >
      <Languages className="language-toggle__icon" size={14} aria-hidden="true" />
      {languageOptions.map((option) => (
        <button
          key={option.locale}
          className={`language-toggle__option${locale === option.locale ? " language-toggle__option--active" : ""}`}
          type="button"
          aria-pressed={locale === option.locale}
          aria-label={text(
            `Switch interface to ${option.name}`,
            `인터페이스를 ${option.name}(으)로 전환`,
          )}
          onClick={() => setLocale(option.locale)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
