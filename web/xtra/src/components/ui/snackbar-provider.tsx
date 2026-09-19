"use client";

import {
    Alert,
    AlertTitle,
    Snackbar,
    type AlertColor,
    type SnackbarCloseReason,
} from "@mui/material";
import {
    createContext,
    useCallback,
    useContext,
    useMemo,
    useState,
    type ReactNode,
    type SyntheticEvent,
} from "react";

type SnackbarMessage = {
    title: string;
    description?: string;
    severity?: AlertColor;
};

type SnackbarContextValue = {
    showSnackbar: (message: SnackbarMessage) => void;
};

const SnackbarContext = createContext<SnackbarContextValue | null>(null);

export function SnackbarProvider({ children }: { children: ReactNode }) {
    const [message, setMessage] = useState<SnackbarMessage | null>(null);
    const [open, setOpen] = useState(false);
    const [messageKey, setMessageKey] = useState(0);

    const showSnackbar = useCallback((nextMessage: SnackbarMessage) => {
        setMessage(nextMessage);
        setMessageKey((current) => current + 1);
        setOpen(true);
    }, []);

    const handleClose = useCallback(
        (_event?: Event | SyntheticEvent, reason?: SnackbarCloseReason) => {
            if (reason === "clickaway") return;
            setOpen(false);
        },
        [],
    );

    const value = useMemo(() => ({ showSnackbar }), [showSnackbar]);

    return (
        <SnackbarContext.Provider value={value}>
            {children}
            <Snackbar
                key={messageKey}
                open={open}
                autoHideDuration={5000}
                onClose={handleClose}
                anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            >
                <Alert
                    severity={message?.severity ?? "info"}
                    variant="filled"
                    onClose={handleClose}
                    sx={{ width: "100%" }}
                >
                    <AlertTitle>{message?.title}</AlertTitle>
                    {message?.description}
                </Alert>
            </Snackbar>
        </SnackbarContext.Provider>
    );
}

export function useSnackbar() {
    const context = useContext(SnackbarContext);
    if (!context) {
        throw new Error("useSnackbar must be used inside SnackbarProvider");
    }
    return context;
}
