import { createNextAuthRoute } from "@credentialengine/auth/server";
import { getAuthConfig } from "@/config/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const handler = createNextAuthRoute(getAuthConfig);
export { handler as GET, handler as POST };
