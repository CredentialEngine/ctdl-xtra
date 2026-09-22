import { getAuthConfig } from "@/config/auth";
import { createLogoutRoute } from "@credentialengine/auth/server";
import { rejectInvalidRequest } from "@server/security/csrf";
import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const logout = createLogoutRoute(getAuthConfig);

async function csrfProtectedLogout(request: NextRequest) {
    const csrfRejection = rejectInvalidRequest(request);
    if (csrfRejection) return csrfRejection;
    return logout(request);
}

export { csrfProtectedLogout as POST };
