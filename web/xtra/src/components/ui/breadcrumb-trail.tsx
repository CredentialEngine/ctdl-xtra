"use client";

import { Breadcrumbs, Link as MuiLink, Typography } from "@mui/material";
import Link from "@/components/ui/route-link";

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
                    <MuiLink
                        key={`${item.href}-${item.label}`}
                        component={Link}
                        href={item.href}
                        color="text.secondary"
                        underline="hover"
                        variant="body2"
                    >
                        {item.label}
                    </MuiLink>
                );
            })}
        </Breadcrumbs>
    );
}
