"use client";

import { BffAuthProvider } from "@credentialengine/auth/client";
import { Suspense } from "react";
import { AnalyticsWithConfig } from "./components/Analytics";
import { XtraAuthProvider } from "./components/auth/AuthProvider";
import { ConfigContextProvider } from "./components/providers/ConfigProvider";
import ThemeRegistry from "./themeRegistry";

export default function Providers({ children }: { children: React.ReactNode }) {
    return (
        <ConfigContextProvider>
            <ThemeRegistry>
                <BffAuthProvider unauthorizedBehavior="anonymous">
                    <XtraAuthProvider>
                        <Suspense fallback={null}>
                            <AnalyticsWithConfig />
                        </Suspense>
                        {children}
                    </XtraAuthProvider>
                </BffAuthProvider>
            </ThemeRegistry>
        </ConfigContextProvider>
    );
}
