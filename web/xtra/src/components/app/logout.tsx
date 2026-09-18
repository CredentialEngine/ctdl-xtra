"use client";

import { useEffect } from "react";
import { useXtraAuth } from "../../../app/components/auth/AuthProvider";

export default function Logout() {
    const { logout } = useXtraAuth();

    useEffect(() => {
        void logout().catch((error) => {
            console.error("Unable to sign out:", error);
        });
    }, [logout]);

    return null;
}
