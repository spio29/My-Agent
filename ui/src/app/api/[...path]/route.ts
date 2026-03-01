import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

const getProxyTarget = () => String(process.env.NEXT_INTERNAL_API_ORIGIN || "http://api:8000").replace(/\/+$/, "");
const getAuthHeaderName = () => String(process.env.NEXT_API_PROXY_AUTH_HEADER || process.env.NEXT_PUBLIC_API_AUTH_HEADER || "Authorization");
const getAuthScheme = () => String(process.env.NEXT_API_PROXY_AUTH_SCHEME || process.env.NEXT_PUBLIC_API_AUTH_SCHEME || "Bearer");
const getFallbackToken = () =>
  String(process.env.NEXT_API_PROXY_TOKEN || process.env.NEXT_PUBLIC_API_TOKEN || "").trim();

const buildUpstreamUrl = (segments: string[], search: string) => {
  const path = segments.length > 0 ? `/${segments.join("/")}` : "";
  return `${getProxyTarget()}${path}${search || ""}`;
};

const injectFallbackAuth = (headers: Headers) => {
  const authHeaderName = getAuthHeaderName();
  const token = getFallbackToken();
  if (!token) return;

  const hasAuthHeader = Array.from(headers.keys()).some((key) => key.toLowerCase() === authHeaderName.toLowerCase());
  if (hasAuthHeader) return;

  if (authHeaderName.toLowerCase() === "authorization") {
    const scheme = getAuthScheme().trim();
    headers.set(authHeaderName, scheme ? `${scheme} ${token}` : token);
    return;
  }
  headers.set(authHeaderName, token);
};

const buildProxyHeaders = (request: NextRequest) => {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower === "host" || HOP_BY_HOP_HEADERS.has(lower)) return;
    headers.set(key, value);
  });
  injectFallbackAuth(headers);
  return headers;
};

type RouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

const proxyRequest = async (request: NextRequest, context: RouteContext) => {
  const resolvedParams = await context.params;
  const path = Array.isArray(resolvedParams.path) ? resolvedParams.path : [];
  const upstreamUrl = buildUpstreamUrl(path, request.nextUrl.search);
  const headers = buildProxyHeaders(request);

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
  };

  const method = request.method.toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    const body = await request.arrayBuffer();
    if (body.byteLength > 0) init.body = body;
  }

  try {
    const upstreamResponse = await fetch(upstreamUrl, init);
    const responseHeaders = new Headers();
    upstreamResponse.headers.forEach((value, key) => {
      if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
        responseHeaders.set(key, value);
      }
    });
    return new NextResponse(upstreamResponse.body, {
      status: upstreamResponse.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown";
    return NextResponse.json(
      {
        detail: "Upstream API tidak dapat diakses.",
        upstream: upstreamUrl,
        error: detail,
      },
      { status: 502 },
    );
  }
};

export async function GET(request: NextRequest, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function OPTIONS(request: NextRequest, context: RouteContext) {
  return proxyRequest(request, context);
}

export async function HEAD(request: NextRequest, context: RouteContext) {
  return proxyRequest(request, context);
}
