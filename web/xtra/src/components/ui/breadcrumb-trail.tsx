"use client";

import { Breadcrumbs, Typography } from "@mui/material";
import Link from "next/link";

export interface BreadcrumbTrailProps {
    items: {
        label: string;
        href: string;
    }[];
}

export default function BreadcrumbTrail({ items }: BreadcrumbTrailProps) {
    return (
        <Breadcrumbs
            aria-label="Breadcrumb"
            separator=">"
            sx={{
                display: { xs: "none", md: "flex" },
                color: "text.secondary",
            }}
        >
            {items.map((item, index) => {
                const current = index === items.length - 1;
                return current ? (
                    <Typography
                        key={`${item.href}-${item.label}`}
                        component="span"
                        color="text.primary"
                        aria-current="page"
                        variant="body2"
                    >
                        {item.label}
                    </Typography>
                ) : (
                    <Link
                        key={`${item.href}-${item.label}`}
                        href={item.href}
                        className="text-sm text-muted-foreground hover:underline"
                    >
                        {item.label}
                    </Link>
                );
            })}
        </Breadcrumbs>
    );
}
