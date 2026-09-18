"use client";
import { Alert, AlertTitle, Snackbar } from "@mui/material";
import { useToast } from "@/components/ui/use-toast";

export function Toaster() {
    const { toasts, dismiss } = useToast();
    return (
        <>
            {toasts.map(
                ({ id, title, description, action, variant, open = true }) => (
                    <Snackbar
                        key={id}
                        open={open}
                        autoHideDuration={6000}
                        onClose={() => dismiss(id)}
                        anchorOrigin={{ vertical: "top", horizontal: "right" }}
                    >
                        <Alert
                            severity={
                                variant === "destructive" ? "error" : "info"
                            }
                            variant="filled"
                            onClose={() => dismiss(id)}
                            sx={{ minWidth: 320 }}
                        >
                            {title ? <AlertTitle>{title}</AlertTitle> : null}
                            {description}
                            {action}
                        </Alert>
                    </Snackbar>
                ),
            )}
        </>
    );
}
