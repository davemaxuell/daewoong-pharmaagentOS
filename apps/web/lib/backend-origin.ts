import "server-only";

/** An explicit external backend takes precedence over Vercel's service binding. */
export function backendOrigin(): string | undefined {
  return (process.env.EXTERNAL_API_BASE_URL?.trim() || process.env.API_BASE_URL?.trim())
    ?.replace(/\/+$/, "");
}
