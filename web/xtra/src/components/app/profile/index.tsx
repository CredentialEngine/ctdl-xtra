"use client";
import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";

import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { useXtraAuth } from "../../../../app/components/auth/AuthProvider";

export default function MyProfile() {
    const { user } = useXtraAuth();

    return (
        <>
            <MuiTypography
                variant="h1"
                component="h1"
                className="text-lg font-semibold md:text-2xl"
            >
                My Profile
            </MuiTypography>
            <Box className="w-full max-w-2xl">
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg">
                            Keycloak identity
                        </CardTitle>
                        <CardDescription>
                            Authentication and password management are handled
                            by Keycloak.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="grid gap-3 text-sm">
                        <Box>
                            <MuiTypography
                                component="span"
                                className="font-medium"
                            >
                                Name:
                            </MuiTypography>{" "}
                            {user?.name || "—"}
                        </Box>
                        <Box>
                            <MuiTypography
                                component="span"
                                className="font-medium"
                            >
                                Email:
                            </MuiTypography>{" "}
                            {user?.email || "—"}
                        </Box>
                    </CardContent>
                </Card>
            </Box>
        </>
    );
}
