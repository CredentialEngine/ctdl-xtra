"use client";

import { bffFetch } from "@/security/bffFetch";
import {
    createContext,
    type ReactNode,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";

export type RuntimeConfig = {
    NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING: string;
    NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME: string;
    NEXT_PUBLIC_NODE_ENV: string;
};

const defaultConfig: RuntimeConfig = {
    NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING: "",
    NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME: "xtra",
    NEXT_PUBLIC_NODE_ENV: "",
};

const ConfigContext = createContext<RuntimeConfig | null>(null);
const storageKey = "credentialEngine.runtimeConfig";

// React Strict Mode intentionally mounts effects twice in development. Keep the
// in-flight request at module scope so both mounts share a single HTTP request.
let runtimeConfigPromise: Promise<RuntimeConfig> | null = null;

function loadRuntimeConfig(): Promise<RuntimeConfig> {
    if (!runtimeConfigPromise) {
        runtimeConfigPromise = bffFetch("/api/config", { cache: "no-store" })
            .then(async (response) => {
                if (!response.ok) {
                    throw new Error(
                        `Could not load runtime config (${response.status})`,
                    );
                }

                return (await response.json()) as RuntimeConfig;
            })
            .catch((error) => {
                // Allow a later mount to retry after a genuine network/server failure.
                runtimeConfigPromise = null;
                throw error;
            });
    }

    return runtimeConfigPromise;
}

function readCachedConfig(): RuntimeConfig | null {
    if (globalThis.window === undefined) {
        return null;
    }

    try {
        const storedConfig =
            globalThis.window.sessionStorage.getItem(storageKey);
        return storedConfig
            ? (JSON.parse(storedConfig) as RuntimeConfig)
            : null;
    } catch {
        return null;
    }
}

export function useConfigContext() {
    const context = useContext(ConfigContext);

    if (!context) {
        throw new Error(
            "useConfigContext must be called inside a ConfigContextProvider",
        );
    }

    return context;
}

export function ConfigContextProvider({
    children,
}: Readonly<{ children: ReactNode }>) {
    const [config, setConfig] = useState<RuntimeConfig>(defaultConfig);

    useEffect(() => {
        queueMicrotask(() => {
            const cachedConfig = readCachedConfig();
            if (cachedConfig) {
                setConfig(cachedConfig);
            }
        });

        void loadRuntimeConfig()
            .then((data) => {
                globalThis.window.sessionStorage.setItem(
                    storageKey,
                    JSON.stringify(data),
                );
                setConfig(data);
            })
            .catch((error: unknown) => {
                console.error("Could not load config:", error);
            });
    }, []);

    const value = useMemo(() => config, [config]);

    return (
        <ConfigContext.Provider value={value}>
            {children}
        </ConfigContext.Provider>
    );
}
