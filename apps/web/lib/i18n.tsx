"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "en" | "ko";

type TextSelector = <T>(en: T, ko: T) => T;

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  text: TextSelector;
};

const STORAGE_KEY = "daewoong-fda-locale";
const COOKIE_KEY = "dli_locale";

const I18nContext = createContext<I18nContextValue | null>(null);

function isLocale(value: string | null | undefined): value is Locale {
  return value === "en" || value === "ko";
}

function readCookieLocale() {
  const match = document.cookie
    .split(";")
    .map((entry) => entry.trim())
    .find((entry) => entry.startsWith(`${COOKIE_KEY}=`));

  const value = match?.slice(COOKIE_KEY.length + 1);
  return isLocale(value) ? value : null;
}

export function I18nProvider({
  children,
  initialLocale = "ko",
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  const [preferenceLoaded, setPreferenceLoaded] = useState(false);

  useEffect(() => {
    const preferenceTask = window.setTimeout(() => {
      let storedLocale: string | null = null;

      try {
        storedLocale = window.localStorage.getItem(STORAGE_KEY);
      } catch {
        // Storage may be unavailable in privacy-restricted browser contexts.
      }

      const preferredLocale =
        (isLocale(storedLocale) && storedLocale) || readCookieLocale() || "ko";

      setLocaleState(preferredLocale);
      setPreferenceLoaded(true);
    }, 0);

    return () => window.clearTimeout(preferenceTask);
  }, []);

  useEffect(() => {
    if (!preferenceLoaded) return;

    document.documentElement.lang = locale;
    document.documentElement.dataset.locale = locale;
    document.cookie = `${COOKIE_KEY}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`;

    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      // The cookie still retains the preference when local storage is blocked.
    }
  }, [locale, preferenceLoaded]);

  useEffect(() => {
    function synchronizePreference(event: StorageEvent) {
      if (event.key === STORAGE_KEY && isLocale(event.newValue)) {
        setLocaleState(event.newValue);
      }
    }

    window.addEventListener("storage", synchronizePreference);
    return () => window.removeEventListener("storage", synchronizePreference);
  }, []);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
  }, []);

  const text = useCallback<TextSelector>(
    (en, ko) => (locale === "ko" ? ko : en),
    [locale],
  );

  const value = useMemo(
    () => ({ locale, setLocale, text }),
    [locale, setLocale, text],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);

  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider.");
  }

  return context;
}

export function BilingualText({
  en,
  ko,
  className,
}: {
  en: ReactNode;
  ko: ReactNode;
  className?: string;
}) {
  const { locale, text } = useI18n();

  return (
    <span className={className} lang={locale}>
      {text(en, ko)}
    </span>
  );
}
