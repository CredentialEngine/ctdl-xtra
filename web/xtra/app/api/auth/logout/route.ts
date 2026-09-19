import { createLogoutRoute } from "@credentialengine/auth/server";
import { getAuthConfig } from "@/config/auth";
import { rejectInvalidMutation } from "@server/security/csrf";
import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const logout = createLogoutRoute(getAuthConfig);

export async function POST(request: NextRequest) {
    const rejection = rejectInvalidMutation(request);
    if (rejection) return rejection;
    return logout(request);
}
