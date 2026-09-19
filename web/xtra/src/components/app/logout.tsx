"use client";

import { useEffect } from "react";
import { useXtraAuth } from "../../../app/components/auth/AuthProvider";
import { AppLoadingScreen } from "@/components/ui/loading-state";

export default function Logout() {
    const { logout } = useXtraAuth();

    useEffect(() => {
        void logout().catch((error) => {
            console.error("Unable to sign out:", error);
        });
    }, [logout]);

    return <AppLoadingScreen label="Signing you out" />;
}
