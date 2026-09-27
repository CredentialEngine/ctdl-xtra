"use client";

import MuiButton, {
    type ButtonProps as MuiButtonProps,
} from "@mui/material/Button";
import {
    forwardRef,
    isValidElement,
    type ElementType,
    type ReactElement,
    type ReactNode,
} from "react";

export interface ButtonProps extends Omit<
    MuiButtonProps,
    "variant" | "size" | "color"
> {
    variant?:
        "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
    size?: "default" | "sm" | "lg" | "icon";
    asChild?: boolean;
}

const variantProps = (variant: ButtonProps["variant"]) => {
    switch (variant) {
        case "destructive":
            return { variant: "contained" as const, color: "error" as const };
        case "outline":
            return { variant: "outlined" as const, color: "primary" as const };
        case "secondary":
            return {
                variant: "contained" as const,
                color: "secondary" as const,
            };
        case "ghost":
            return { variant: "text" as const, color: "primary" as const };
        case "link":
            return { variant: "text" as const, color: "primary" as const };
        default:
            return { variant: "contained" as const, color: "primary" as const };
    }
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
    { variant = "default", size = "default", asChild, children, sx, ...props },
    ref,
) {
    const vp = variantProps(variant as ButtonProps["variant"]);
    const muiSize =
        size === "sm" ? "small" : size === "lg" ? "large" : "medium";
    const commonSx = {
        ...(size === "icon"
            ? { minWidth: 40, width: 40, height: 40, p: 0 }
            : {}),
        ...(variant === "link"
            ? { textDecoration: "underline", textUnderlineOffset: 4 }
            : {}),
        ...sx,
    };
    if (asChild && isValidElement(children)) {
        const child = children as ReactElement<{ children?: ReactNode }>;
        return (
            <MuiButton
                ref={ref}
                {...vp}
                size={muiSize}
                component={child.type as ElementType}
                {...child.props}
                {...props}
                sx={commonSx}
            >
                {child.props.children}
            </MuiButton>
        );
    }
    return (
        <MuiButton ref={ref} {...vp} size={muiSize} {...props} sx={commonSx}>
            {children}
        </MuiButton>
    );
});

export { Button };
