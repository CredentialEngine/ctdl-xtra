"use client";

import { useXtraAuth } from "../../../app/components/auth/AuthProvider";
import LoginIcon from "@mui/icons-material/Login";
import {
    Box,
    Button,
    Card,
    CardContent,
    CircularProgress,
    Typography,
} from "@mui/material";
import { useState } from "react";

export default function Login() {
    const { login } = useXtraAuth();
    const [signingIn, setSigningIn] = useState(false);

    return (
        <Card
            variant="outlined"
            sx={{
                width: "100%",
                maxWidth: 460,
                borderRadius: 2,
                overflow: "hidden",
            }}
        >
            <Box
                sx={{
                    bgcolor: "primary.main",
                    color: "primary.contrastText",
                    px: 4,
                    py: 3,
                    display: "flex",
                    alignItems: "center",
                    gap: 2,
                }}
            >
                <Box
                    component="img"
                    src="/logo.png"
                    alt="CTDL xTRA"
                    sx={{
                        height: 48,
                        width: "auto",
                        bgcolor: "background.paper",
                        borderRadius: 1,
                        p: 0.5,
                    }}
                />
                <Box>
                    <Typography variant="h5" sx={{ fontWeight: 700 }}>
                        CTDL xTRA
                    </Typography>
                    <Typography variant="body2" sx={{ opacity: 0.88 }}>
                        Credential Engine
                    </Typography>
                </Box>
            </Box>
            <CardContent sx={{ p: 4 }}>
                <Typography
                    variant="h5"
                    component="h1"
                    sx={{ fontWeight: 700 }}
                    gutterBottom
                >
                    Sign in
                </Typography>
                <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 3 }}
                >
                    Use your Credential Engine account to continue.
                    Authentication is handled securely by the xTRA BFF and
                    Keycloak.
                </Typography>
                <Button
                    type="button"
                    variant="contained"
                    fullWidth
                    size="large"
                    disabled={signingIn}
                    startIcon={
                        signingIn ? (
                            <CircularProgress size={18} color="inherit" />
                        ) : (
                            <LoginIcon />
                        )
                    }
                    onClick={() => {
                        setSigningIn(true);
                        login("/");
                    }}
                >
                    {signingIn
                        ? "Redirecting to sign in…"
                        : "Sign in with Credential Engine"}
                </Button>
            </CardContent>
        </Card>
    );
}
