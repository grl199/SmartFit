import { NextRequest, NextResponse } from "next/server";

type RouteContext = { params: Promise<{ path: string[] }> };

const API_TARGET = (
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000"
).replace(/\/+$/, "");

async function forward(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const pathname = path.map((segment) => encodeURIComponent(segment)).join("/");
  const target = `${API_TARGET}/${pathname}${request.nextUrl.search}`;
  const headers = new Headers();
  const accessToken = request.cookies.get("smartfit_access")?.value;

  const method = request.method.toUpperCase();
  if (accessToken) headers.set("authorization", `Bearer ${accessToken}`);
  if (accessToken && !["GET", "HEAD", "OPTIONS"].includes(method)) {
    const origin = request.headers.get("origin");
    if (!origin || origin !== request.nextUrl.origin) {
      return NextResponse.json({ detail: "Origen no permitido" }, { status: 403 });
    }
  }

  for (const name of ["accept", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const body = method === "GET" || method === "HEAD"
    ? undefined
    : await request.arrayBuffer();

  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });

    const responseHeaders = new Headers();
    for (const name of ["content-type", "content-disposition", "retry-after"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    responseHeaders.set("cache-control", "no-store");

    return new Response(
      method === "HEAD" || upstream.status === 204 || upstream.status === 304
        ? null
        : upstream.body,
      { status: upstream.status, headers: responseHeaders },
    );
  } catch (error) {
    console.error(`SmartFit API proxy failed (${target})`, error);
    return NextResponse.json(
      {
        detail: `No se pudo conectar con SmartFit API en ${API_TARGET}. Comprueba que el backend está iniciado y accesible.`,
      },
      { status: 502 },
    );
  }
}

export const GET = forward;
export const HEAD = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
