import { rejectInvalidRequest } from "@server/security/csrf";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
    const csrfRejection = rejectInvalidRequest(request);
    if (csrfRejection) return csrfRejection;

    return NextResponse.json(
        {
            NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING:
                process.env
                    .NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING ?? "",
            NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME:
                process.env.NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME ??
                "xtra",
            NEXT_PUBLIC_NODE_ENV:
                process.env.NEXT_PUBLIC_NODE_ENV ?? process.env.NODE_ENV ?? "",
        },
        {
            headers: {
                "Cache-Control": "no-store, max-age=0",
            },
        },
    );
}
