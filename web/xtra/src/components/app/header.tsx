"use client";

import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import LoginIcon from "@mui/icons-material/Login";
import MenuIcon from "@mui/icons-material/Menu";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import {
    AppBar,
    Box,
    Button,
    Divider,
    IconButton,
    Menu,
    MenuItem,
    Toolbar,
    Tooltip,
    useMediaQuery,
} from "@mui/material";
import Link from "@/components/ui/route-link";
import { usePathname } from "next/navigation";
import { useState, type RefObject } from "react";
import { useXtraAuth } from "../../../app/components/auth/AuthProvider";

export type HeaderLink = {
    label: string;
    href: string;
};

type HeaderProps = {
    links?: HeaderLink[];
    showNavigationMenu?: boolean;
    onNavigationMenuClick?: () => void;
    navigationMenuButtonRef?: RefObject<HTMLButtonElement | null>;
};

export default function Header({
    links = [],
    showNavigationMenu = false,
    onNavigationMenuClick,
    navigationMenuButtonRef,
}: Readonly<HeaderProps>) {
    const pathname = usePathname();
    const isNarrow = useMediaQuery("(max-width:999.95px)");
    const { user, login } = useXtraAuth();
    const authenticated = Boolean(user);
    const [overflowAnchor, setOverflowAnchor] = useState<null | HTMLElement>(
        null,
    );
    const [userAnchor, setUserAnchor] = useState<null | HTMLElement>(null);

    // Use one explicit responsive breakpoint for the header. Below 1000px,
    // application pages switch to the hamburger and header links move into
    // the vertical overflow menu. Header-only pages still use the same
    // overflow breakpoint even though they have no left navigation to open.
    const showHamburger = showNavigationMenu && isNarrow;
    const showHeaderOverflow = links.length > 0 && isNarrow;
    const showInlineHeaderLinks = links.length > 0 && !isNarrow;
    const centerLogo = isNarrow;

    const handleHamburger = () => {
        onNavigationMenuClick?.();
    };

    return (
        <AppBar
            component="header"
            position="fixed"
            sx={{
                zIndex: (theme) => theme.zIndex.drawer + 1,
                borderBottom: 1,
                borderColor: "divider",
            }}
        >
            <Toolbar
                sx={{
                    minHeight: "64px !important",
                    gap: 1.5,
                    position: "relative",
                }}
            >
                {showHamburger && (
                    <IconButton
                        ref={navigationMenuButtonRef}
                        color="inherit"
                        edge="start"
                        aria-label="Open navigation"
                        onClick={handleHamburger}
                    >
                        <MenuIcon aria-hidden="true" />
                    </IconButton>
                )}

                <Link
                    href="/"
                    aria-label="CTDL xTRA home"
                    style={{
                        display: "inline-flex",
                        alignItems: "center",
                        color: "inherit",
                        textDecoration: "none",
                    }}
                >
                    <Box
                        component="img"
                        src="/logo.png"
                        alt="CTDL xTRA"
                        sx={{
                            height: "3rem",
                            width: "auto",
                            maxWidth: { xs: "8rem", sm: "9rem" },
                            objectFit: "contain",
                            bgcolor: "common.white",
                            borderRadius: 0.5,
                            px: 1,
                            py: 0.5,
                            ...(centerLogo
                                ? {
                                      position: "absolute",
                                      left: "50%",
                                      transform: "translateX(-50%)",
                                  }
                                : {}),
                        }}
                    />
                </Link>

                <Box sx={{ flexGrow: 1 }} />

                {showInlineHeaderLinks && (
                    <Box
                        component="nav"
                        aria-label="Header navigation"
                        sx={{ display: "flex", alignItems: "center", gap: 0.5 }}
                    >
                        {links.map((link) => (
                            <Button
                                key={link.href}
                                component={Link}
                                href={link.href}
                                color="inherit"
                                aria-current={
                                    pathname === link.href ? "page" : undefined
                                }
                            >
                                {link.label}
                            </Button>
                        ))}
                    </Box>
                )}

                {showHeaderOverflow && (
                    <Tooltip title="More">
                        <IconButton
                            color="inherit"
                            aria-label="More header links"
                            aria-haspopup="menu"
                            aria-expanded={Boolean(overflowAnchor)}
                            onClick={(event) =>
                                setOverflowAnchor(event.currentTarget)
                            }
                            sx={{ width: 40, height: 40 }}
                        >
                            <MoreVertIcon aria-hidden="true" />
                        </IconButton>
                    </Tooltip>
                )}

                <Box sx={{ display: "flex", alignItems: "center" }}>
                    {authenticated ? (
                        <>
                            <Tooltip title="Profile">
                                <IconButton
                                    color="inherit"
                                    aria-label="Open profile menu"
                                    aria-haspopup="menu"
                                    aria-expanded={Boolean(userAnchor)}
                                    aria-controls={
                                        userAnchor ? "profile-menu" : undefined
                                    }
                                    onClick={(event) =>
                                        setUserAnchor(event.currentTarget)
                                    }
                                    sx={{
                                        width: 40,
                                        height: 40,
                                    }}
                                >
                                    <AccountCircleIcon aria-hidden="true" />
                                </IconButton>
                            </Tooltip>
                            <Menu
                                id="profile-menu"
                                disableScrollLock
                                anchorEl={userAnchor}
                                open={Boolean(userAnchor)}
                                onClose={() => setUserAnchor(null)}
                                anchorOrigin={{
                                    vertical: "bottom",
                                    horizontal: "right",
                                }}
                                transformOrigin={{
                                    vertical: "top",
                                    horizontal: "right",
                                }}
                            >
                                <MenuItem
                                    component={Link}
                                    href="/profile"
                                    onClick={() => setUserAnchor(null)}
                                >
                                    My Profile
                                </MenuItem>
                                <Divider />
                                <MenuItem
                                    component={Link}
                                    href="/logout"
                                    onClick={() => setUserAnchor(null)}
                                >
                                    Logout
                                </MenuItem>
                            </Menu>
                        </>
                    ) : (
                        <Button
                            color="inherit"
                            startIcon={<LoginIcon />}
                            onClick={() =>
                                login(pathname === "/" ? "/" : pathname)
                            }
                        >
                            Log In
                        </Button>
                    )}
                </Box>
            </Toolbar>

            <Menu
                disableScrollLock
                anchorEl={overflowAnchor}
                open={Boolean(overflowAnchor)}
                onClose={() => setOverflowAnchor(null)}
                anchorOrigin={{
                    vertical: "bottom",
                    horizontal: "right",
                }}
                transformOrigin={{
                    vertical: "top",
                    horizontal: "right",
                }}
            >
                {links.map((link) => (
                    <MenuItem
                        key={link.href}
                        component={Link}
                        href={link.href}
                        onClick={() => setOverflowAnchor(null)}
                    >
                        {link.label}
                    </MenuItem>
                ))}
            </Menu>
        </AppBar>
    );
}
