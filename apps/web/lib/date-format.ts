import type { Locale } from "@/lib/i18n";

const KST_OFFSET_MINUTES = 9 * 60;
const DEFAULT_OPTIONS: Intl.DateTimeFormatOptions = {
  day: "2-digit",
  month: "short",
  year: "numeric",
};

const EN_MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const EN_MONTHS_LONG = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

type DateParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

function pad(value: number, width = 2) {
  return String(value).padStart(width, "0");
}

function parseDateParts(value: string): DateParts | null {
  const dateOnly = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) {
    return {
      year: Number(dateOnly[1]),
      month: Number(dateOnly[2]),
      day: Number(dateOnly[3]),
      hour: 0,
      minute: 0,
      second: 0,
    };
  }

  const englishDate = value.match(/^(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})$/);
  if (englishDate) {
    const monthIndex = EN_MONTHS_SHORT.indexOf(englishDate[2]);
    if (monthIndex >= 0) {
      return {
        year: Number(englishDate[3]),
        month: monthIndex + 1,
        day: Number(englishDate[1]),
        hour: 0,
        minute: 0,
        second: 0,
      };
    }
  }

  const zonelessDateTime = value.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$/,
  );
  const parsed = zonelessDateTime
    ? new Date(Date.UTC(
        Number(zonelessDateTime[1]),
        Number(zonelessDateTime[2]) - 1,
        Number(zonelessDateTime[3]),
        Number(zonelessDateTime[4]),
        Number(zonelessDateTime[5]),
        Number(zonelessDateTime[6] ?? 0),
      ))
    : new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;

  // The portal's operational clock is KST. Applying its fixed modern offset and
  // reading UTC fields avoids host/browser timezone and ICU-data differences.
  const kst = new Date(parsed.getTime() + KST_OFFSET_MINUTES * 60_000);
  return {
    year: kst.getUTCFullYear(),
    month: kst.getUTCMonth() + 1,
    day: kst.getUTCDate(),
    hour: kst.getUTCHours(),
    minute: kst.getUTCMinutes(),
    second: kst.getUTCSeconds(),
  };
}

function formatMonth(month: number, style: Intl.DateTimeFormatOptions["month"], locale: Locale) {
  if (locale === "ko") {
    const number = style === "2-digit" ? pad(month) : String(month);
    return `${number}월`;
  }
  if (style === "long") return EN_MONTHS_LONG[month - 1];
  if (style === "narrow") return EN_MONTHS_LONG[month - 1][0];
  if (style === "numeric") return String(month);
  if (style === "2-digit") return pad(month);
  return EN_MONTHS_SHORT[month - 1];
}

function usesTwelveHourClock(options: Intl.DateTimeFormatOptions, locale: Locale) {
  if (typeof options.hour12 === "boolean") return options.hour12;
  if (options.hourCycle === "h11" || options.hourCycle === "h12") return true;
  if (options.hourCycle === "h23" || options.hourCycle === "h24") return false;
  return locale === "ko";
}

export function formatPortalDate(
  value: string,
  options: Intl.DateTimeFormatOptions = DEFAULT_OPTIONS,
  locale: Locale = "en",
) {
  if (!value) return locale === "ko" ? "기록 없음" : "Not recorded";
  const parts = parseDateParts(value);
  if (!parts) return value;

  const dateParts: string[] = [];
  const year = options.year === "2-digit" ? pad(parts.year % 100) : String(parts.year);
  const day = options.day === "2-digit" ? pad(parts.day) : String(parts.day);
  const month = options.month ? formatMonth(parts.month, options.month, locale) : "";

  if (locale === "ko") {
    if (options.year) dateParts.push(`${year}년`);
    if (options.month) dateParts.push(month);
    if (options.day) dateParts.push(`${day}일`);
  } else {
    if (options.day) dateParts.push(day);
    if (options.month) dateParts.push(month);
    if (options.year) dateParts.push(year);
  }

  let time = "";
  if (options.hour) {
    const twelveHour = usesTwelveHourClock(options, locale);
    let displayHour = parts.hour;
    if (twelveHour) displayHour = parts.hour % 12 || 12;
    else if (options.hourCycle === "h24" && displayHour === 0) displayHour = 24;

    const hour = options.hour === "2-digit" ? pad(displayHour) : String(displayHour);
    const clockParts = [hour];
    if (options.minute) clockParts.push(options.minute === "2-digit" ? pad(parts.minute) : String(parts.minute));
    if (options.second) clockParts.push(options.second === "2-digit" ? pad(parts.second) : String(parts.second));
    const clock = clockParts.join(":");

    if (twelveHour) {
      const dayPeriod = locale === "ko"
        ? parts.hour < 12 ? "오전" : "오후"
        : parts.hour < 12 ? "AM" : "PM";
      time = locale === "ko" ? `${dayPeriod} ${clock}` : `${clock} ${dayPeriod}`;
    } else {
      time = clock;
    }
  }

  const date = dateParts.join(" ");
  if (!date) return time;
  if (!time) return date;
  return locale === "ko" ? `${date} ${time}` : `${date}, ${time}`;
}
