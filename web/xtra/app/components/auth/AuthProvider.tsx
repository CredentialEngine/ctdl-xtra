"use client";

import {
    type AuthenticatedUser,
    useBffAuth,
} from "@credentialengine/auth/client";
import {
    createContext,
    type ReactNode,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";
import { getClientCsrfToken } from "@/security/csrfClient";

type AuthContextValue = {
    user: AuthenticatedUser | undefined;
    csrfToken: string | undefined;
    isLoading: boolean;
    login: (callbackUrl?: string) => void;
    logout: () => Promise<void>;
    refresh: () => Promise<boolean>;
    hasRole: (role: string) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useXtraAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error("useXtraAuth must be used inside XtraAuthProvider");
    }
    return context;
}

export function XtraAuthProvider({
    children,
}: Readonly<{ children: ReactNode }>) {
    const {
        user,
        isLoading: authLoading,
        login,
        refresh,
        hasRole,
    } = useBffAuth();
    const [csrfToken, setCsrfToken] = useState<string | undefined>();

    useEffect(() => {
        let cancelled = false;

        void getClientCsrfToken()
            .then((token) => {
                if (!cancelled) setCsrfToken(token);
            })
            .catch((error) => {
                console.error("Unable to initialize CSRF protection:", error);
            });

        return () => {
            cancelled = true;
        };
    }, []);

    const logout = useCallback(async () => {
        const callbackUrl = "/";
        const freshCsrfToken = await getClientCsrfToken(true);
        setCsrfToken(freshCsrfToken);

        const response = await fetch("/api/auth/logout", {
            method: "POST",
            credentials: "include",
            cache: "no-store",
            headers: {
                "X-CSRF-Token": freshCsrfToken,
            },
        });

        if (!response.ok) {
            throw new Error(`Logout failed (HTTP ${response.status})`);
        }

        window.location.replace(callbackUrl);
    }, []);

    const isLoading = authLoading || !csrfToken;
    const value = useMemo(
        () => ({
            user,
            csrfToken,
            isLoading,
            login,
            logout,
            refresh,
            hasRole,
        }),
        [user, csrfToken, isLoading, login, logout, refresh, hasRole],
    );

    return (
        <AuthContext.Provider value={value}>
            {csrfToken ? children : null}
        </AuthContext.Provider>
    );
}
