import { next } from "@vercel/functions";
import { checkBotId } from "botid/server";

const BOT_PROTECTED_POST_PATHS = new Set([
  "/api/coach",
  "/api/drills/generate",
  "/api/echo/transcribe",
]);

function isProtected(request: Request): boolean {
  if (request.method !== "POST") return false;
  const pathname = new URL(request.url).pathname;
  return BOT_PROTECTED_POST_PATHS.has(pathname) || pathname.startsWith("/api/echo/reveals/");
}

export default async function middleware(request: Request) {
  if (!isProtected(request)) return next();

  let verification: Awaited<ReturnType<typeof checkBotId>>;
  try {
    verification = await checkBotId({
      advancedOptions: { checkLevel: "basic" },
    });
  } catch {
    return Response.json(
      {
        detail: {
          code: "ai_guard_unavailable",
          message: "AI verification is briefly unavailable. Offline practice still works.",
        },
      },
      { status: 503 },
    );
  }

  if (verification.isBot) {
    return Response.json(
      {
        detail: {
          code: "bot_blocked",
          message: "This request could not be verified. Please retry from the Dấu app.",
        },
      },
      { status: 403 },
    );
  }

  const headers = new Headers(request.headers);
  // Routing Middleware always overwrites this private assertion, so an incoming
  // client header cannot impersonate a verified browser.
  headers.set("x-dau-bot-verified", "1");
  return next({ request: { headers } });
}

export const config = {
  matcher: [
    "/api/coach",
    "/api/drills/generate",
    "/api/echo/transcribe",
    "/api/echo/reveals/:path*",
  ],
  runtime: "nodejs",
};
