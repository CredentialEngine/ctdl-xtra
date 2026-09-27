import { randomBytes, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

export const CSRF_COOKIE_NAME = "xtra.csrf";
export const CSRF_HEADER_NAME = "x-csrf-token";

export function createCsrfToken(): string {
    return randomBytes(32).toString("base64url");
}

function safeEqual(left: string, right: string): boolean {
    const leftBuffer = Buffer.from(left);
    const rightBuffer = Buffer.from(right);

    return (
        leftBuffer.length === rightBuffer.length &&
        timingSafeEqual(leftBuffer, rightBuffer)
    );
}

export function hasValidCsrfToken(request: NextRequest): boolean {
    const cookieToken = request.cookies.get(CSRF_COOKIE_NAME)?.value;
    const headerToken = request.headers.get(CSRF_HEADER_NAME);

    return Boolean(
        cookieToken && headerToken && safeEqual(cookieToken, headerToken),
    );
}

export function rejectInvalidRequest(
    request: NextRequest,
): NextResponse | null {
    if (!hasValidCsrfToken(request)) {
        return NextResponse.json(
            { error: "Invalid or missing CSRF token" },
            { status: 403 },
        );
    }

    return null;
}

/** @deprecated Use rejectInvalidRequest; CSRF is required for all SPA BFF requests. */
export const rejectInvalidMutation = rejectInvalidRequest;
