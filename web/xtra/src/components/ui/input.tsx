"use client";
import TextField, { type TextFieldProps } from "@mui/material/TextField";
import React from "react";
export type InputProps = Omit<TextFieldProps, "variant">;
const Input = React.forwardRef<HTMLInputElement, InputProps>(
    ({ type, size = "small", ...props }, ref) => (
        <TextField
            inputRef={ref}
            type={type}
            variant="outlined"
            size={size}
            fullWidth
            {...props}
        />
    ),
);
Input.displayName = "Input";
export { Input };
