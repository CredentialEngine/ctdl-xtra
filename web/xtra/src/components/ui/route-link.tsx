"use client";

import NextLink, { type LinkProps as NextLinkProps } from "next/link";
import { usePathname } from "next/navigation";
import { forwardRef, type AnchorHTMLAttributes, type MouseEvent } from "react";

export const NAVIGATION_START_EVENT = "xtra:navigation-start";

export function startNavigation(href?: string) {
    if (typeof window !== "undefined") {
        const pathname = href
            ? new URL(href, window.location.href).pathname
            : undefined;
        window.dispatchEvent(
            new CustomEvent(NAVIGATION_START_EVENT, {
                detail: { pathname },
            }),
        );
    }
}

type RouteLinkProps = NextLinkProps &
    Omit<AnchorHTMLAttributes<HTMLAnchorElement>, keyof NextLinkProps>;

const RouteLink = forwardRef<HTMLAnchorElement, RouteLinkProps>(
    function RouteLink({ href, onClick, prefetch, ...props }, ref) {
        const pathname = usePathname();
        const hrefPathname =
            typeof href === "string"
                ? href.split(/[?#]/, 1)[0] || "/"
                : href.pathname;
        const isCurrentPath = Boolean(
            hrefPathname && hrefPathname === pathname,
        );

        const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
            onClick?.(event);
            if (event.defaultPrevented) return;

            // Preserve normal browser behavior for modified clicks, new tabs,
            // downloads, and non-left-button interactions.
            if (
                event.button !== 0 ||
                event.metaKey ||
                event.ctrlKey ||
                event.shiftKey ||
                event.altKey ||
                props.target === "_blank" ||
                props.download
            ) {
                return;
            }

            const target = new URL(
                typeof href === "string" ? href : (href.pathname ?? ""),
                window.location.href,
            );
            const current = new URL(window.location.href);
            const sameLocation =
                target.origin === current.origin &&
                target.pathname === current.pathname &&
                target.search === current.search &&
                target.hash === current.hash;

            if (sameLocation) {
                event.preventDefault();
                return;
            }

            if (target.origin === current.origin) startNavigation(target.href);
        };

        return (
            <NextLink
                ref={ref}
                href={href}
                prefetch={isCurrentPath ? false : prefetch}
                onClick={handleClick}
                {...props}
            />
        );
    },
);

export default RouteLink;
