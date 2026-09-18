"use client";
import {
    Card as MuiCard,
    CardContent as MuiCardContent,
    CardActions,
    Box,
    Typography,
} from "@mui/material";
import React from "react";

const Card = React.forwardRef<
    HTMLDivElement,
    React.ComponentProps<typeof MuiCard>
>(({ sx, ...props }, ref) => (
    <MuiCard
        ref={ref}
        variant="outlined"
        {...props}
        sx={{ borderRadius: 2, ...sx }}
    />
));
Card.displayName = "Card";
const CardHeader = React.forwardRef<
    HTMLDivElement,
    React.ComponentProps<typeof Box>
>(({ sx, ...props }, ref) => (
    <Box ref={ref} {...props} sx={{ p: 3, pb: 1.5, ...sx }} />
));
CardHeader.displayName = "CardHeader";
const CardTitle = React.forwardRef<
    HTMLParagraphElement,
    React.ComponentProps<typeof Typography>
>(({ sx, ...props }, ref) => (
    <Typography
        ref={ref}
        variant="h6"
        component="h3"
        {...props}
        sx={{ fontWeight: 700, ...sx }}
    />
));
CardTitle.displayName = "CardTitle";
const CardDescription = React.forwardRef<
    HTMLParagraphElement,
    React.ComponentProps<typeof Typography>
>(({ sx, ...props }, ref) => (
    <Typography
        ref={ref}
        variant="body2"
        color="text.secondary"
        {...props}
        sx={sx}
    />
));
CardDescription.displayName = "CardDescription";
const CardContent = React.forwardRef<
    HTMLDivElement,
    React.ComponentProps<typeof MuiCardContent>
>(({ sx, ...props }, ref) => (
    <MuiCardContent
        ref={ref}
        {...props}
        sx={{ p: 3, pt: 1.5, "&:last-child": { pb: 3 }, ...sx }}
    />
));
CardContent.displayName = "CardContent";
const CardFooter = React.forwardRef<
    HTMLDivElement,
    React.ComponentProps<typeof CardActions>
>(({ sx, ...props }, ref) => (
    <CardActions ref={ref} {...props} sx={{ px: 3, pb: 3, pt: 0, ...sx }} />
));
CardFooter.displayName = "CardFooter";
export {
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardContent,
    CardFooter,
};
