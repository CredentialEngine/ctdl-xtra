import { getAuthConfig } from "@/config/auth";
import {
    BffUnauthorizedError,
    getAuthenticatedUser,
} from "@credentialengine/auth/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
    try {
        const user = await getAuthenticatedUser(await getAuthConfig());
        if (!user) {
            return Response.json(
                { error: "Not authenticated", code: "UNAUTHORIZED" },
                { status: 401 },
            );
        }

        return Response.json(user, {
            headers: { "Cache-Control": "no-store" },
        });
    } catch (error) {
        if (error instanceof BffUnauthorizedError) {
            return Response.json(
                { error: error.message, code: error.code },
                { status: 401 },
            );
        }
        throw error;
    }
}
