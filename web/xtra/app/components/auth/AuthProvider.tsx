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
    useRef,
    useState,
} from "react";
import { bffFetch } from "@/security/bffFetch";
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
    const logoutPromiseRef = useRef<Promise<void> | null>(null);

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

    const logout = useCallback(() => {
        if (logoutPromiseRef.current) {
            return logoutPromiseRef.current;
        }

        const logoutPromise = (async () => {
            const response = await bffFetch("/api/auth/logout", {
                method: "POST",
                cache: "no-store",
            });

            if (!response.ok) {
                throw new Error(`Logout failed (HTTP ${response.status})`);
            }

            window.location.replace("/");
        })();

        logoutPromiseRef.current = logoutPromise;
        void logoutPromise.catch(() => {
            logoutPromiseRef.current = null;
        });
        return logoutPromise;
    }, []);

    const isLoading = authLoading;
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
        <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
    );
}
