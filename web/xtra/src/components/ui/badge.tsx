"use client";
import Chip, { type ChipProps } from "@mui/material/Chip";
import React from "react";
export interface BadgeProps extends Omit<
    ChipProps,
    "variant" | "color" | "children" | "label"
> {
    variant?: "default" | "secondary" | "destructive" | "outline";
    children?: React.ReactNode;
}
const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
    ({ variant = "default", children, ...props }, ref) => {
        const color =
            variant === "destructive"
                ? "error"
                : variant === "secondary"
                  ? "secondary"
                  : "primary";
        return (
            <Chip
                ref={ref}
                size="small"
                label={children}
                color={color}
                variant={variant === "outline" ? "outlined" : "filled"}
                {...props}
            />
        );
    },
);
Badge.displayName = "Badge";
const badgeVariants = () => "";
export { Badge, badgeVariants };
