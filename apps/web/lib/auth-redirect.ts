export function safeAuthCallbackUrl(value: string | string[] | undefined) {
  if (typeof value !== "string") return "/dashboard";
  try {
    const base = new URL("https://portal.invalid");
    const destination = new URL(value, base);
    if (destination.origin === base.origin && value.startsWith("/")) {
      return `${destination.pathname}${destination.search}${destination.hash}`;
    }
  } catch {
    // Invalid callback values fall through to the portal home.
  }
  return "/dashboard";
}
