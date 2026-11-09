// Thin wrapper around the Telegram WebApp SDK (loaded via <script> in
// index.html per Telegram's own docs — not an npm package). Falls back to
// safe no-ops when not running inside Telegram (e.g. the dev-sim path
// below, or a plain browser tab opened by mistake) so screens never have
// to null-check window.Telegram themselves.

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: { start_param?: string };
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  ready: () => void;
  expand: () => void;
  close: () => void;
  onEvent: (event: string, cb: () => void) => void;
  offEvent: (event: string, cb: () => void) => void;
  BackButton: { show: () => void; hide: () => void; onClick: (cb: () => void) => void; offClick: (cb: () => void) => void };
  HapticFeedback?: { notificationOccurred: (type: "success" | "error" | "warning") => void; impactOccurred: (style: string) => void };
}

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}

export function getWebApp(): TelegramWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function initTelegramUi(): void {
  const webApp = getWebApp();
  if (!webApp) return;
  webApp.ready();
  webApp.expand();
  applyThemeVars(webApp.themeParams);
  webApp.onEvent("themeChanged", () => applyThemeVars(webApp.themeParams));
}

function applyThemeVars(params: Record<string, string>): void {
  const root = document.documentElement.style;
  for (const [key, value] of Object.entries(params)) {
    root.setProperty(`--tg-theme-${key.replace(/_/g, "-")}`, value);
  }
}

export function haptic(type: "success" | "error" | "warning"): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

/** Real Telegram initData, or null if this tab wasn't opened by Telegram. */
export function getInitData(): string | null {
  const data = getWebApp()?.initData;
  return data && data.length > 0 ? data : null;
}

export function getStartParam(): string | null {
  return getWebApp()?.initDataUnsafe.start_param ?? null;
}

export function getThemeParams(): Record<string, string> {
  return getWebApp()?.themeParams ?? {};
}

/**
 * Dev-only stand-in for opening this app inside real Telegram. Builds an
 * `initData` string signed exactly the way app/core/security.py verifies
 * it, using the backend's documented *placeholder* dev bot token
 * (server/app/core/config.py: "dev-placeholder-bot-token", the default
 * when BOT_TOKEN is unset) — not a secret, so this is not a bypass of
 * anything. Lets `npm run dev` be tested end-to-end in a plain browser
 * without a real Telegram client. Never reachable in a production build
 * (gated by import.meta.env.DEV at the one call site in AuthContext).
 */
export async function buildDevInitData(botToken: string, telegramId: number, firstName: string): Promise<string> {
  const authDate = Math.floor(Date.now() / 1000);
  const user = JSON.stringify({ id: telegramId, first_name: firstName, language_code: "en" });
  const pairs: Record<string, string> = { auth_date: String(authDate), user };

  const dataCheckString = Object.keys(pairs)
    .sort()
    .map((k) => `${k}=${pairs[k]}`)
    .join("\n");

  const secretKey = await hmacSha256Raw(new TextEncoder().encode("WebAppData"), botToken);
  const hash = await hmacSha256Hex(secretKey, dataCheckString);

  const params = new URLSearchParams({ ...pairs, hash });
  return params.toString();
}

async function hmacSha256Raw(keyBytes: Uint8Array, message: string): Promise<ArrayBuffer> {
  const key = await crypto.subtle.importKey("raw", keyBytes as BufferSource, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message) as BufferSource);
}

async function hmacSha256Hex(keyBytes: ArrayBuffer, message: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message) as BufferSource);
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
