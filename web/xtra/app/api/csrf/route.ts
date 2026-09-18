import { createCsrfToken, CSRF_COOKIE_NAME } from "@server/security/csrf";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
    const csrfToken = createCsrfToken();
    const response = NextResponse.json(
        { csrfToken },
        { headers: { "Cache-Control": "no-store" } },
    );

    response.cookies.set(CSRF_COOKIE_NAME, csrfToken, {
        httpOnly: true,
        sameSite: "strict",
        secure: request.nextUrl.protocol === "https:",
        path: "/",
        maxAge: 60 * 60 * 8,
    });

    return response;
}
