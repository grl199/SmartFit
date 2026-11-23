import { NextRequest, NextResponse } from "next/server";

const API_TARGET = (
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000"
).replace(/\/+$/, "");

const secure = process.env.NODE_ENV === "production";
const sameSite = "lax" as const;
const accessCookie = "smartfit_access";
const refreshCookie = "smartfit_refresh";

function assertSameOrigin(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!origin || origin !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Origen no permitido" }, { status: 403 });
  }
  return null;
}

function setSessionCookies(response: NextResponse, access: string, refresh: string) {
  response.cookies.set(accessCookie, access, {
    httpOnly: true, secure, sameSite, path: "/", maxAge: 15 * 60,
  });
  response.cookies.set(refreshCookie, refresh, {
    httpOnly: true, secure, sameSite, path: "/api/auth", maxAge: 30 * 24 * 60 * 60,
  });
}

function clearSessionCookies(response: NextResponse) {
  response.cookies.set(accessCookie, "", { httpOnly: true, secure, sameSite, path: "/", maxAge: 0 });
  response.cookies.set(refreshCookie, "", { httpOnly: true, secure, sameSite, path: "/api/auth", maxAge: 0 });
}

async function postBackend(path: string, body: unknown, access?: string) {
  return fetch(`${API_TARGET}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(access ? { authorization: `Bearer ${access}` } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
}

export async function POST(request: NextRequest, context: { params: Promise<{ action: string }> }) {
  const denied = assertSameOrigin(request);
  if (denied) return denied;
  const { action } = await context.params;

  if (action === "login" || action === "register") {
    const body = await request.json();
    const upstream = await postBackend(`/auth/session/${action}`, body);
    const payload = await upstream.json();
    if (!upstream.ok) return NextResponse.json(payload, { status: upstream.status });
    const response = NextResponse.json({ user: payload.user }, { status: upstream.status });
    setSessionCookies(response, payload.access_token, payload.refresh_token);
    return response;
  }

  if (action === "refresh") {
    const refresh = request.cookies.get(refreshCookie)?.value;
    if (!refresh) {
      const response = NextResponse.json({ detail: "Sesión no válida o caducada" }, { status: 401 });
      clearSessionCookies(response);
      return response;
    }
    const upstream = await postBackend("/auth/session/refresh", { refresh_token: refresh });
    const payload = await upstream.json();
    if (!upstream.ok) {
      const response = NextResponse.json(payload, { status: upstream.status });
      clearSessionCookies(response);
      return response;
    }
    const response = NextResponse.json({ user: payload.user });
    setSessionCookies(response, payload.access_token, payload.refresh_token);
    return response;
  }

  if (action === "logout") {
    const access = request.cookies.get(accessCookie)?.value;
    const refresh = request.cookies.get(refreshCookie)?.value;
    if (refresh) await postBackend("/auth/session/logout", { refresh_token: refresh }, access).catch(() => undefined);
    const response = NextResponse.json({ ok: true });
    clearSessionCookies(response);
    return response;
  }

  return NextResponse.json({ detail: "Ruta no encontrada" }, { status: 404 });
}
