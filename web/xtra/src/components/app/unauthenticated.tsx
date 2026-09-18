"use client";

import { Box } from "@mui/material";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import Login from "./login";
import Logout from "./logout";

export default function Unauthenticated() {
    const pathname = usePathname();
    const router = useRouter();

    useEffect(() => {
        if (pathname !== "/" && pathname !== "/logout") {
            router.replace("/");
        }
    }, [pathname, router]);

    return (
        <Box
            sx={{
                width: "100%",
                minHeight: "100vh",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                p: 2,
                bgcolor: "background.default",
            }}
        >
            {pathname === "/logout" ? (
                <Logout />
            ) : pathname === "/" ? (
                <Login />
            ) : null}
        </Box>
    );
}
