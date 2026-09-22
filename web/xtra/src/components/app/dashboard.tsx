"use client";

import ExpandLessIcon from "@mui/icons-material/ChevronLeft";
import ExpandMoreIcon from "@mui/icons-material/ChevronRight";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import LanguageIcon from "@mui/icons-material/Language";
import CloudDownloadIcon from "@mui/icons-material/CloudDownload";
import ScienceIcon from "@mui/icons-material/Science";
import WorkspacesIcon from "@mui/icons-material/SpaceDashboard";
import RunsIcon from "@mui/icons-material/FactCheck";
import StrategiesIcon from "@mui/icons-material/AccountTree";
import PublishIcon from "@mui/icons-material/Publish";
import {
    Box,
    Drawer,
    IconButton,
    List,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    LinearProgress,
    Tooltip,
    useMediaQuery,
    useTheme,
} from "@mui/material";
import {
    useEffect,
    useRef,
    useState,
    type KeyboardEvent as ReactKeyboardEvent,
    type PointerEvent as ReactPointerEvent,
    type ReactNode,
} from "react";
import Link, { NAVIGATION_START_EVENT } from "@/components/ui/route-link";
import { usePathname } from "next/navigation";
import { useXtraAuth } from "../../../app/components/auth/AuthProvider";
import Header, { type HeaderLink } from "@/components/app/header";

const defaultExpandedWidth = 280;
const collapsedWidth = 72;
const minExpandedWidth = 180;
const maxExpandedWidth = 440;
const navWidthStorageKey = "ctdl-xtra-nav-width";
const navCollapsedStorageKey = "ctdl-xtra-nav-collapsed";

const sourceItems = [
    {
        to: "/sources/all",
        label: "All Sources",
        icon: <LanguageIcon fontSize="small" />,
    },
    {
        to: "/crawls",
        label: "Crawl Runs",
        icon: <CloudDownloadIcon fontSize="small" />,
    },
];

const benchmarkItems = [
    {
        to: "/benchmarks/workspaces",
        label: "Workspaces",
        icon: <WorkspacesIcon fontSize="small" />,
    },
    {
        to: "/benchmarks/runs",
        label: "Runs",
        icon: <RunsIcon fontSize="small" />,
    },
    {
        to: "/benchmarks/strategies",
        label: "Strategies",
        icon: <StrategiesIcon fontSize="small" />,
    },
];

const publishingItems = [
    {
        to: "/publishing/runs",
        label: "ETL Runs",
        icon: <RunsIcon fontSize="small" />,
    },
];

type NavigationChild = {
    to: string;
    label: string;
    icon: ReactNode;
};

const headerLinks: HeaderLink[] = [{ href: "/about", label: "About" }];

// Header destinations use the full-width content layout. The primary left
// navigation is reserved for the application's main workspace routes.
const headerOnlyRoutes = new Set([
    ...headerLinks.map((link) => link.href),
    "/profile",
]);

export function Dashboard({ children }: Readonly<{ children: ReactNode }>) {
    const location = usePathname();
    const { user } = useXtraAuth();
    const authenticated = Boolean(user);
    const showPrimaryNavigation =
        authenticated && !headerOnlyRoutes.has(location);
    const theme = useTheme();
    const isDesktop = useMediaQuery("(min-width:1000px)");
    const [collapsed, setCollapsed] = useState(false);
    const [expandedWidth, setExpandedWidth] = useState(defaultExpandedWidth);
    const [resizingNav, setResizingNav] = useState(false);
    const navPreferencesLoaded = useRef(false);
    const [sourceExpanded, setSourceExpanded] = useState(true);
    const [benchmarkExpanded, setBenchmarkExpanded] = useState(true);
    const [publishingExpanded, setPublishingExpanded] = useState(true);
    const [mobileOpen, setMobileOpen] = useState(false);
    const mobileMenuButtonRef = useRef<HTMLButtonElement>(null);
    const mobileNavigationRef = useRef<HTMLElement>(null);
    const [navigationTarget, setNavigationTarget] = useState<string | null>(
        null,
    );
    const navigationPending =
        navigationTarget !== null && navigationTarget !== location;
    const drawerWidth = collapsed ? collapsedWidth : expandedWidth;
    const iconOnlyNavigation = collapsed;
    const lastComfortableExpandedWidth = useRef(defaultExpandedWidth);
    const sourceActive =
        location.startsWith("/sources") || location.startsWith("/crawls");
    const benchmarkActive = location.startsWith("/benchmarks");
    const publishingActive = location.startsWith("/publishing");

    useEffect(() => {
        const storedWidth = Number(
            window.localStorage.getItem(navWidthStorageKey),
        );
        const storedCollapsed = window.localStorage.getItem(
            navCollapsedStorageKey,
        );
        const frame = window.requestAnimationFrame(() => {
            if (
                Number.isFinite(storedWidth) &&
                storedWidth > collapsedWidth &&
                storedWidth <= maxExpandedWidth
            ) {
                setExpandedWidth(storedWidth);
                if (storedWidth >= minExpandedWidth)
                    lastComfortableExpandedWidth.current = storedWidth;
            }
            if (storedCollapsed === "true" || storedCollapsed === "false") {
                setCollapsed(storedCollapsed === "true");
            }
            navPreferencesLoaded.current = true;
        });
        return () => window.cancelAnimationFrame(frame);
    }, []);

    useEffect(() => {
        const handleNavigationStart = (event: Event) => {
            const navigationEvent = event as CustomEvent<{ pathname?: string }>;
            setNavigationTarget(
                navigationEvent.detail?.pathname ?? window.location.pathname,
            );
        };
        const handleHistoryNavigation = () => {
            // Browser Back/Forward does not emit NAVIGATION_START_EVENT. Clear
            // any target left by the previous in-app navigation so the progress
            // bar cannot remain pending after a popstate navigation.
            setNavigationTarget(null);
        };

        window.addEventListener(NAVIGATION_START_EVENT, handleNavigationStart);
        window.addEventListener("popstate", handleHistoryNavigation);
        return () => {
            window.removeEventListener(
                NAVIGATION_START_EVENT,
                handleNavigationStart,
            );
            window.removeEventListener("popstate", handleHistoryNavigation);
        };
    }, []);

    useEffect(() => {
        if (!navPreferencesLoaded.current) return;
        window.localStorage.setItem(navWidthStorageKey, String(expandedWidth));
        window.localStorage.setItem(navCollapsedStorageKey, String(collapsed));
    }, [collapsed, expandedWidth]);

    const applyNavigationWidth = (width: number) => {
        // Keep the drawer width continuous while dragging. It only becomes the
        // fully collapsed icon rail when the user reaches the collapsed width.
        const nextWidth = Math.min(
            maxExpandedWidth,
            Math.max(collapsedWidth, width),
        );
        if (nextWidth <= collapsedWidth) {
            setCollapsed(true);
            return;
        }

        setCollapsed(false);
        setExpandedWidth(nextWidth);
        if (nextWidth >= minExpandedWidth)
            lastComfortableExpandedWidth.current = nextWidth;
    };

    const openMobileNavigation = () => {
        // MUI's temporary Drawer hides the rest of the application from assistive
        // technology while open. Move focus out of that soon-to-be-hidden tree
        // before opening the modal, then place focus inside the drawer.
        mobileMenuButtonRef.current?.blur();
        setMobileOpen(true);
        window.requestAnimationFrame(() =>
            mobileNavigationRef.current?.focus(),
        );
    };

    const closeMobileNavigation = (restoreFocus = true) => {
        // The temporary MUI Drawer remains mounted while its closing transition
        // runs. If focus is still inside the Drawer when MUI marks the hidden
        // modal aria-hidden, browsers correctly warn that focused content has
        // been hidden from assistive technology. Clear focus before closing and
        // restore it to the menu button after the close has been committed.
        if (document.activeElement instanceof HTMLElement) {
            document.activeElement.blur();
        }

        setMobileOpen(false);

        if (restoreFocus) {
            window.requestAnimationFrame(() =>
                mobileMenuButtonRef.current?.focus(),
            );
        }
    };

    const toggleNavigationCollapsed = () => {
        if (collapsed) {
            setExpandedWidth(
                Math.max(
                    minExpandedWidth,
                    lastComfortableExpandedWidth.current,
                ),
            );
            setCollapsed(false);
            return;
        }

        if (expandedWidth >= minExpandedWidth)
            lastComfortableExpandedWidth.current = expandedWidth;
        setCollapsed(true);
    };

    const beginNavigationResize = (
        event: ReactPointerEvent<HTMLDivElement>,
    ) => {
        if (!isDesktop) return;
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        setResizingNav(true);

        const onPointerMove = (moveEvent: PointerEvent) =>
            applyNavigationWidth(moveEvent.clientX);
        const finish = () => {
            setResizingNav(false);
            document.body.style.removeProperty("cursor");
            document.body.style.removeProperty("user-select");
            window.removeEventListener("pointermove", onPointerMove);
            window.removeEventListener("pointerup", finish);
            window.removeEventListener("pointercancel", finish);
        };

        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        window.addEventListener("pointermove", onPointerMove);
        window.addEventListener("pointerup", finish);
        window.addEventListener("pointercancel", finish);
    };

    const handleNavigationResizeKeyDown = (
        event: ReactKeyboardEvent<HTMLDivElement>,
    ) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();

        if (collapsed) {
            if (event.key === "ArrowRight") toggleNavigationCollapsed();
            return;
        }

        const delta = event.key === "ArrowRight" ? 16 : -16;
        applyNavigationWidth(drawerWidth + delta);
    };

    const navGroup = ({
        id,
        rootPath,
        label,
        icon,
        active,
        expanded,
        setExpanded,
        items,
    }: {
        id: string;
        rootPath: string;
        label: string;
        icon: ReactNode;
        active: boolean;
        expanded: boolean;
        setExpanded: (value: boolean | ((current: boolean) => boolean)) => void;
        items: NavigationChild[];
    }) => (
        <Box sx={{ mb: 0.5 }}>
            {iconOnlyNavigation ? (
                <Tooltip title={`Open ${label}`} placement="right">
                    <ListItemButton
                        component={Link}
                        href={rootPath}
                        selected={active}
                        aria-label={`Open ${label}`}
                        aria-current={
                            location === rootPath ? "page" : undefined
                        }
                        sx={{
                            borderRadius: 1,
                            minHeight: 46,
                            px: 1.5,
                            justifyContent: "center",
                            mb: 0.25,
                            position: "relative",
                        }}
                    >
                        <ListItemIcon
                            sx={{
                                minWidth: 0,
                                color: active
                                    ? "secondary.main"
                                    : "text.secondary",
                                justifyContent: "center",
                            }}
                        >
                            {icon}
                        </ListItemIcon>
                    </ListItemButton>
                </Tooltip>
            ) : (
                <Box
                    sx={{
                        display: "grid",
                        gridTemplateColumns: "minmax(0, 1fr) 40px",
                        alignItems: "stretch",
                        mb: 0.25,
                        bgcolor: active ? "action.selected" : "transparent",
                    }}
                >
                    <ListItemButton
                        component={Link}
                        href={rootPath}
                        selected={location === rootPath}
                        aria-current={
                            location === rootPath ? "page" : undefined
                        }
                        sx={{
                            minHeight: 46,
                            px: 2,
                            display: "grid",
                            gridTemplateColumns: "40px minmax(0, 1fr)",
                            alignItems: "center",
                            borderRadius: 0,
                        }}
                    >
                        <ListItemIcon
                            sx={{
                                minWidth: 0,
                                color: active
                                    ? "secondary.main"
                                    : "text.secondary",
                                justifyContent: "flex-start",
                            }}
                        >
                            {icon}
                        </ListItemIcon>
                        <ListItemText
                            primary={label}
                            sx={{ minWidth: 0, m: 0 }}
                            slotProps={{
                                primary: {
                                    noWrap: true,
                                    sx: { fontWeight: active ? 700 : 500 },
                                },
                            }}
                        />
                    </ListItemButton>
                    <IconButton
                        aria-label={`${expanded ? "Collapse" : "Expand"} ${label}`}
                        aria-expanded={expanded}
                        aria-controls={`${id}-navigation-items`}
                        onClick={() => setExpanded((value) => !value)}
                        sx={{ borderRadius: 0 }}
                    >
                        {expanded ? (
                            <KeyboardArrowDownIcon
                                fontSize="small"
                                aria-hidden="true"
                            />
                        ) : (
                            <KeyboardArrowRightIcon
                                fontSize="small"
                                aria-hidden="true"
                            />
                        )}
                    </IconButton>
                </Box>
            )}

            {(expanded || iconOnlyNavigation) && (
                <Box
                    id={`${id}-navigation-items`}
                    aria-label={`${label} navigation`}
                    sx={{
                        mt: 0.5,
                        p: iconOnlyNavigation ? 0.5 : 0.75,
                        borderRadius: 1.5,
                        bgcolor: "action.hover",
                    }}
                >
                    <List disablePadding>
                        {items.map((item) => {
                            const selected =
                                location === item.to ||
                                location.startsWith(`${item.to}/`);
                            const child = (
                                <ListItemButton
                                    key={item.to}
                                    component={Link}
                                    href={item.to}
                                    selected={selected}
                                    aria-label={
                                        iconOnlyNavigation
                                            ? `${label}: ${item.label}`
                                            : undefined
                                    }
                                    aria-current={selected ? "page" : undefined}
                                    onClick={() => closeMobileNavigation(false)}
                                    sx={{
                                        borderRadius: 1,
                                        minHeight: iconOnlyNavigation ? 42 : 38,
                                        px: iconOnlyNavigation ? 1.25 : 1.5,
                                        justifyContent: iconOnlyNavigation
                                            ? "center"
                                            : "flex-start",
                                        mb: 0.25,
                                        position: "relative",
                                        transition:
                                            "background-color 120ms ease, color 120ms ease",
                                        "&:last-of-type": { mb: 0 },
                                        "&.Mui-selected": {
                                            bgcolor:
                                                "var(--ce-panel-strong-bg)",
                                            color: "var(--ce-panel-strong-text)",
                                            "&:hover": {
                                                bgcolor:
                                                    "var(--ce-panel-strong-bg)",
                                            },
                                            "& .MuiListItemIcon-root": {
                                                color: "var(--ce-panel-strong-text)",
                                            },
                                        },
                                    }}
                                >
                                    <ListItemIcon
                                        sx={{
                                            minWidth: iconOnlyNavigation
                                                ? 0
                                                : 34,
                                            color: selected
                                                ? "inherit"
                                                : "text.secondary",
                                            justifyContent: "center",
                                        }}
                                    >
                                        {item.icon}
                                    </ListItemIcon>
                                    {!iconOnlyNavigation && (
                                        <ListItemText
                                            primary={item.label}
                                            slotProps={{
                                                primary: {
                                                    noWrap: true,
                                                    sx: {
                                                        fontSize: "1rem",
                                                        fontWeight: selected
                                                            ? 700
                                                            : 500,
                                                    },
                                                },
                                            }}
                                        />
                                    )}
                                </ListItemButton>
                            );
                            return iconOnlyNavigation ? (
                                <Tooltip
                                    key={item.to}
                                    title={`${label}: ${item.label}`}
                                    placement="right"
                                >
                                    {child}
                                </Tooltip>
                            ) : (
                                child
                            );
                        })}
                    </List>
                </Box>
            )}
        </Box>
    );

    const navigation = (
        <Box
            component="nav"
            ref={mobileNavigationRef}
            tabIndex={isDesktop ? undefined : -1}
            aria-label="Primary navigation"
            sx={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                bgcolor: "sidebar.background",
                position: "relative",
            }}
        >
            <List sx={{ p: 1.5, flex: 1 }}>
                {navGroup({
                    id: "sources",
                    rootPath: "/sources",
                    label: "Sources",
                    icon: <LanguageIcon />,
                    active: sourceActive,
                    expanded: sourceExpanded,
                    setExpanded: setSourceExpanded,
                    items: sourceItems,
                })}

                {navGroup({
                    id: "benchmarks",
                    rootPath: "/benchmarks",
                    label: "Benchmarks",
                    icon: <ScienceIcon />,
                    active: benchmarkActive,
                    expanded: benchmarkExpanded,
                    setExpanded: setBenchmarkExpanded,
                    items: benchmarkItems,
                })}

                {navGroup({
                    id: "publishing",
                    rootPath: "/publishing",
                    label: "Publishing",
                    icon: <PublishIcon />,
                    active: publishingActive,
                    expanded: publishingExpanded,
                    setExpanded: setPublishingExpanded,
                    items: publishingItems,
                })}
            </List>

            {isDesktop && (
                <Tooltip
                    title={
                        collapsed ? "Expand navigation" : "Collapse navigation"
                    }
                    placement="right"
                >
                    <IconButton
                        aria-label={
                            collapsed
                                ? "Expand navigation"
                                : "Collapse navigation"
                        }
                        onClick={toggleNavigationCollapsed}
                        size="small"
                        sx={{
                            position: "absolute",
                            right: collapsed ? "50%" : 12,
                            bottom: 12,
                            transform: collapsed ? "translateX(50%)" : "none",
                            width: 34,
                            height: 34,
                            minWidth: 34,
                            maxWidth: 34,
                            minHeight: 34,
                            maxHeight: 34,
                            p: 0,
                            aspectRatio: "1 / 1",
                            boxSizing: "border-box",
                            flex: "0 0 34px",
                            borderRadius: "9999px !important",
                            overflow: "hidden",
                            border: 1,
                            borderColor: "sidebar.border",
                            bgcolor: "background.paper",
                            boxShadow: 1,
                            "&:hover": { bgcolor: "action.hover" },
                        }}
                    >
                        {collapsed ? (
                            <ExpandMoreIcon
                                fontSize="small"
                                aria-hidden="true"
                            />
                        ) : (
                            <ExpandLessIcon
                                fontSize="small"
                                aria-hidden="true"
                            />
                        )}
                    </IconButton>
                </Tooltip>
            )}
        </Box>
    );

    return (
        <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
            <Box
                component="a"
                href="#main-content"
                sx={{
                    position: "fixed",
                    left: 8,
                    top: 8,
                    zIndex: (t) => t.zIndex.tooltip + 1,
                    transform: "translateY(-150%)",
                    bgcolor: "background.paper",
                    color: "text.primary",
                    px: 2,
                    py: 1,
                    borderRadius: 1,
                    "&:focus": { transform: "translateY(0)" },
                }}
            >
                Skip to main content
            </Box>

            <Header
                links={headerLinks}
                showNavigationMenu={showPrimaryNavigation}
                onNavigationMenuClick={openMobileNavigation}
                navigationMenuButtonRef={mobileMenuButtonRef}
            />

            {showPrimaryNavigation && navigationPending && (
                <LinearProgress
                    aria-label="Loading page"
                    sx={{
                        position: "fixed",
                        top: 64,
                        left: { xs: 0, md: `${drawerWidth}px` },
                        right: 0,
                        zIndex: (t) => t.zIndex.drawer + 2,
                        transition: resizingNav ? "none" : "left 120ms ease",
                    }}
                />
            )}

            {showPrimaryNavigation && (
                <Drawer
                    variant={isDesktop ? "permanent" : "temporary"}
                    open={isDesktop || mobileOpen}
                    onClose={() => closeMobileNavigation()}
                    ModalProps={{
                        keepMounted: true,
                        disableRestoreFocus: true,
                    }}
                    sx={{
                        width: isDesktop ? drawerWidth : defaultExpandedWidth,
                        flexShrink: 0,
                        "& .MuiDrawer-paper": {
                            width: isDesktop
                                ? drawerWidth
                                : defaultExpandedWidth,
                            boxSizing: "border-box",
                            mt: "64px",
                            height: "calc(100% - 64px)",
                            borderRightColor: "sidebar.border",
                            transition: resizingNav
                                ? "none"
                                : theme.transitions.create("width", {
                                      duration:
                                          theme.transitions.duration.shorter,
                                  }),
                            overflowX: "hidden",
                        },
                    }}
                >
                    {navigation}
                    {isDesktop && (
                        <Box
                            role="separator"
                            aria-label="Resize primary navigation"
                            aria-orientation="vertical"
                            aria-valuemin={collapsedWidth}
                            aria-valuemax={maxExpandedWidth}
                            aria-valuenow={drawerWidth}
                            aria-valuetext={
                                collapsed
                                    ? "Navigation collapsed to icons"
                                    : `Navigation width ${drawerWidth} pixels`
                            }
                            tabIndex={0}
                            onPointerDown={beginNavigationResize}
                            onKeyDown={handleNavigationResizeKeyDown}
                            sx={{
                                position: "absolute",
                                top: 0,
                                right: 0,
                                bottom: 0,
                                width: 8,
                                cursor: "col-resize",
                                zIndex: 2,
                                touchAction: "none",
                                outline: "none",
                                "&::after": {
                                    content: '""',
                                    position: "absolute",
                                    top: 0,
                                    bottom: 0,
                                    left: "50%",
                                    width: 2,
                                    transform: "translateX(-50%)",
                                    bgcolor: resizingNav
                                        ? "secondary.main"
                                        : "transparent",
                                    transition: theme.transitions.create(
                                        "background-color",
                                        {
                                            duration:
                                                theme.transitions.duration
                                                    .shortest,
                                        },
                                    ),
                                },
                                "&:hover::after, &:focus-visible::after": {
                                    bgcolor: "secondary.main",
                                },
                                "&:focus-visible": {
                                    boxShadow: `0 0 0 2px ${theme.palette.secondary.main}`,
                                },
                            }}
                        />
                    )}
                </Drawer>
            )}

            <Box
                component="main"
                id="main-content"
                tabIndex={-1}
                sx={{
                    ml:
                        showPrimaryNavigation && isDesktop
                            ? `${drawerWidth}px`
                            : 0,
                    pt: "64px",
                    minHeight: "100vh",
                    transition: resizingNav
                        ? "none"
                        : theme.transitions.create("margin", {
                              duration: theme.transitions.duration.shorter,
                          }),
                }}
            >
                <Box
                    sx={{
                        p: { xs: 2, md: 3 },
                        maxWidth: 1600,
                        mx: "auto",
                        color: "text.primary",
                        "& .MuiTypography-root": { color: "inherit" },
                        "& .MuiTypography-colorTextSecondary": {
                            color: "text.secondary",
                        },
                    }}
                >
                    {children}
                </Box>
            </Box>
        </Box>
    );
}
