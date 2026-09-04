import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import localFont from "next/font/local";
import { BilingualText, I18nProvider, type Locale } from "@/lib/i18n";
import "./globals.css";
import "./typography-scale.css";

const pretendard = localFont({
  src: "./fonts/PretendardVariable.woff2",
  weight: "100 900",
  style: "normal",
  variable: "--font-pretendard",
  display: "swap",
  fallback: ["Apple SD Gothic Neo", "Noto Sans KR", "Inter", "system-ui", "sans-serif"],
});

export const metadata: Metadata = {
  title: {
    default: "FDA Warning Letter Update · FDA 경고서한 업데이트",
    template: "%s · Daewoong",
  },
  description:
    "Search and analyze FDA drug warning letters with grounded bilingual answers. 근거 기반의 한영 답변으로 FDA 의약품 경고서한을 검색하고 분석합니다.",
  applicationName: "FDA Warning Letter Update · FDA 경고서한 업데이트",
};

export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#ffffff",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get("dli_locale")?.value;
  const initialLocale: Locale = cookieLocale === "en" ? "en" : "ko";

  return (
    <html
      lang={initialLocale}
      data-scroll-behavior="smooth"
      suppressHydrationWarning
      className={pretendard.variable}
    >
      <body className={pretendard.className}>
        <I18nProvider initialLocale={initialLocale}>
          <a className="skip-link" href="#main-content">
            <BilingualText en="Skip to main content" ko="본문으로 건너뛰기" />
          </a>
          {children}
        </I18nProvider>
      </body>
    </html>
  );
}
