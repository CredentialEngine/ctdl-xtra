"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";
import { useXtraAuth } from "../app/components/auth/AuthProvider";
import { Dashboard } from "@/components/app/dashboard";
import Unauthenticated from "@/components/app/unauthenticated";
import Logout from "@/components/app/logout";

const SESSION_KEEPALIVE_MS = 2 * 60 * 1000;

export default function ClientApp({
    children,
}: Readonly<{ children: ReactNode }>) {
    const { user, isLoading, login, refresh } = useXtraAuth();
    const pathname = usePathname();
    const hadAuthenticatedUser = useRef(false);

    useEffect(() => {
        if (!user) return;

        hadAuthenticatedUser.current = true;
        const keepAlive = window.setInterval(() => {
            void refresh().then((authenticated) => {
                if (!authenticated && hadAuthenticatedUser.current) {
                    const callbackUrl =
                        `${window.location.pathname}${window.location.search}${window.location.hash}` ||
                        "/";
                    login(callbackUrl);
                }
            });
        }, SESSION_KEEPALIVE_MS);

        return () => window.clearInterval(keepAlive);
    }, [login, refresh, user]);

    if (isLoading) return null;
    if (!user) return <Unauthenticated />;
    if (pathname === "/logout") return <Logout />;

    return <Dashboard>{children}</Dashboard>;
}
