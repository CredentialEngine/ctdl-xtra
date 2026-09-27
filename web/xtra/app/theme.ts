import {
    createTheme,
    type PaletteMode,
    type ThemeOptions,
} from "@mui/material/styles";

export const lightPalette = {
    // Credential Engine brand palette:
    // navy #23375C, green #45A085, orange #E8A66B, white #FFFFFF.
    background: "#FFFFFF",
    paper: "#FFFFFF",
    surface: "rgba(35, 55, 92, 0.05)",
    text: "#000000",
    textSecondary: "#000000",
    primary: "#23375C",
    primaryContrast: "#FFFFFF",
    secondary: "#45A085",
    secondaryContrast: "#000000",
    accent: "#E8A66B",
    aquaDark: "#45A085",
    accentSoft: "rgba(232, 166, 107, 0.18)",
    border: "#23375C",
    divider: "rgba(35, 55, 92, 0.30)",
    link: "#000000",
    focus: "#E8A66B",
    actionAquaBg: "#45A085",
    actionAquaText: "#000000",
    actionBlueBg: "#23375C",
    actionBlueText: "#FFFFFF",
    actionBrownBg: "#E8A66B",
    actionBrownText: "#000000",
    panelStrongBg: "#45A085",
    panelStrongText: "#000000",
    cardSelectedBg: "rgba(69, 160, 133, 0.16)",
    sidebar: "#FFFFFF",
    sidebarBorder: "rgba(35, 55, 92, 0.30)",
    sidebarHover: "rgba(69, 160, 133, 0.14)",
    footer: "rgba(35, 55, 92, 0.05)",
    envDev: { background: "#E8A66B", text: "#000000" },
    envStaging: { background: "#45A085", text: "#000000" },
};

export const darkPalette = {
    // Keep the page canvas deliberately darker than the Credential Engine
    // brand navy. The brand navy belongs to the logo/identity; green and
    // orange carry interaction while white remains the dark-mode text color.
    background: "#071821",
    paper: "#0C2230",
    surface: "#132E40",
    text: "#FFFFFF",
    textSecondary: "#FFFFFF",
    primary: "#45A085",
    primaryContrast: "#000000",
    secondary: "#E8A66B",
    secondaryContrast: "#000000",
    accent: "#E8A66B",
    aquaDark: "#45A085",
    accentSoft: "rgba(232, 166, 107, 0.18)",
    border: "#3C5668",
    divider: "#2B4557",
    link: "#FFFFFF",
    focus: "#E8A66B",
    actionAquaBg: "#45A085",
    actionAquaText: "#000000",
    actionBlueBg: "#132E40",
    actionBlueText: "#FFFFFF",
    actionBrownBg: "#E8A66B",
    actionBrownText: "#000000",
    panelStrongBg: "#45A085",
    panelStrongText: "#FFFFFF",
    cardSelectedBg: "rgba(69, 160, 133, 0.24)",
    sidebar: "#0B202E",
    sidebarBorder: "#294558",
    sidebarHover: "#153548",
    footer: "#0B202E",
    envDev: { background: "#E8A66B", text: "#000000" },
    envStaging: { background: "#45A085", text: "#000000" },
};

export const applyColorSchemeVariables = (mode: PaletteMode) => {
    const palette = mode === "dark" ? darkPalette : lightPalette;

    if (typeof globalThis.document === "undefined") return;

    const root = globalThis.document.documentElement;
    root.dataset.theme = mode;
    root.classList.toggle("dark", mode === "dark");
    root.style.colorScheme = mode;
    root.style.setProperty("--ce-background", palette.background);
    root.style.setProperty("--ce-paper", palette.paper);
    root.style.setProperty("--ce-surface", palette.surface);
    root.style.setProperty("--ce-text", palette.text);
    root.style.setProperty("--ce-text-secondary", palette.textSecondary);
    root.style.setProperty("--ce-blue-dark", palette.primary);
    root.style.setProperty("--ce-brown", palette.focus);
    root.style.setProperty("--ce-grey-dark", palette.textSecondary);
    root.style.setProperty("--ce-grey-light", palette.divider);
    root.style.setProperty("--ce-aqua-dark", palette.aquaDark);
    root.style.setProperty("--ce-aqua-light", palette.accentSoft);
    root.style.setProperty("--ce-white", palette.paper);
    root.style.setProperty("--ce-link", palette.link);
    root.style.setProperty("--ce-border", palette.border);
    root.style.setProperty("--ce-focus", palette.focus);
    root.style.setProperty("--ce-action-aqua-bg", palette.actionAquaBg);
    root.style.setProperty("--ce-action-aqua-text", palette.actionAquaText);
    root.style.setProperty("--ce-action-blue-bg", palette.actionBlueBg);
    root.style.setProperty("--ce-action-blue-text", palette.actionBlueText);
    root.style.setProperty("--ce-action-brown-bg", palette.actionBrownBg);
    root.style.setProperty("--ce-action-brown-text", palette.actionBrownText);
    root.style.setProperty("--ce-panel-strong-bg", palette.panelStrongBg);
    root.style.setProperty("--ce-panel-strong-text", palette.panelStrongText);
    root.style.setProperty("--ce-card-selected-bg", palette.cardSelectedBg);
};

const breakpoints = {
    values: {
        xs: 0,
        sm: 500,
        md: 1000,
        lg: 1300,
        xl: 1800,
    },
};

export const createAppTheme = (mode: PaletteMode = "light") => {
    const palette = mode === "dark" ? darkPalette : lightPalette;

    const themeOptions: ThemeOptions = {
        // Intentionally use MUI's default typography/font stack.
        // Use a 12px-equivalent root (75% of the browser default 16px), while
        // keeping typography in rem so browser zoom and user font preferences scale cleanly.
        // Explicit heading variants preserve visual hierarchy instead of flattening headings
        // into the default body1 Typography variant.
        typography: {
            h1: { fontSize: "2rem", lineHeight: 1.2, fontWeight: 700 },
            h2: { fontSize: "1.5rem", lineHeight: 1.25, fontWeight: 700 },
            h3: { fontSize: "1.25rem", lineHeight: 1.3, fontWeight: 700 },
            h4: { fontSize: "1.125rem", lineHeight: 1.35, fontWeight: 700 },
            h5: { fontSize: "1.0625rem", lineHeight: 1.4, fontWeight: 700 },
            h6: { fontSize: "1rem", lineHeight: 1.4, fontWeight: 700 },
            body1: { fontSize: "1rem", lineHeight: 1.5 },
            body2: { fontSize: "1rem", lineHeight: 1.5 },
            subtitle1: { fontSize: "1rem", lineHeight: 1.5 },
            subtitle2: { fontSize: "1rem", lineHeight: 1.5 },
            button: { fontSize: "1rem", lineHeight: 1.5 },
            caption: { fontSize: "1rem", lineHeight: 1.5 },
            overline: { fontSize: "1rem", lineHeight: 1.5 },
        },
        palette: {
            mode,
            background: {
                default: palette.background,
                paper: palette.paper,
            },
            text: {
                primary: palette.text,
                secondary: palette.textSecondary,
            },
            divider: palette.divider,
            primary: {
                main: palette.primary,
                contrastText: palette.primaryContrast,
            },
            secondary: {
                main: palette.secondary,
                contrastText: palette.secondaryContrast,
            },
            error: {
                main: mode === "dark" ? "#FFB4AB" : "#8B0000",
                light: mode === "dark" ? "#FFDAD6" : "#B3261E",
                contrastText: mode === "dark" ? "#2D0000" : "#FFFFFF",
            },
            sidebar: {
                background: palette.sidebar,
                border: palette.sidebarBorder,
                hoverBackground: palette.sidebarHover,
            },
            envChip: {
                development: palette.envDev,
                staging: palette.envStaging,
            },
            footer: {
                background: palette.footer,
            },
            link: {
                default: palette.link,
                hover: palette.link,
            },
            blueDark: "var(--ce-blue-dark)",
            brown: "var(--ce-brown)",
            greyDark: "var(--ce-grey-dark)",
            greyLight: "var(--ce-grey-light)",
            aquaDark: "var(--ce-aqua-dark)",
            aquaLight: "var(--ce-aqua-light)",
            white: "var(--ce-white)",
            selected: palette.cardSelectedBg,
        },
        breakpoints,
        components: {
            MuiCssBaseline: {
                styleOverrides: {
                    html: {
                        fontSize: "75%",
                        // Keep the viewport gutter stable so overlays never
                        // resize the page when they open or close.
                        scrollbarGutter: "stable",
                    },
                    body: {
                        backgroundColor: palette.background,
                        color: palette.text,
                        fontSize: "1rem",
                    },
                    a: { color: palette.link },
                    "*:focus-visible": {
                        outline: `3px solid ${palette.focus}`,
                        outlineOffset: "3px",
                    },
                },
            },
            // MUI overlays normally lock document scrolling while open. That
            // removes the browser scrollbar and causes the entire layout to
            // jump horizontally. Disable scroll locking once at the theme
            // level so every menu, select, popover and modal-based overlay
            // keeps the page width stable.
            MuiModal: {
                defaultProps: { disableScrollLock: true },
            },
            MuiPopover: {
                defaultProps: { disableScrollLock: true },
            },
            MuiMenu: {
                defaultProps: { disableScrollLock: true },
            },
            MuiDialog: {
                defaultProps: { disableScrollLock: true },
            },
            MuiDrawer: {
                defaultProps: {
                    ModalProps: { disableScrollLock: true },
                },
            },
            MuiSelect: {
                defaultProps: {
                    MenuProps: { disableScrollLock: true },
                },
            },
            MuiContainer: {
                defaultProps: { maxWidth: "lg" },
            },
            MuiButton: {
                defaultProps: { disableElevation: true },
                styleOverrides: {
                    root: {
                        borderRadius: "0.5rem",
                        fontSize: "1rem",
                        fontWeight: 700,
                        textTransform: "none",
                    },
                },
            },
            MuiFormHelperText: {
                styleOverrides: {
                    root: { fontSize: "1rem", lineHeight: 1.5 },
                },
            },
            MuiInputLabel: {
                styleOverrides: {
                    root: { fontSize: "1rem" },
                },
            },
            MuiTooltip: {
                styleOverrides: {
                    tooltip: { fontSize: "1rem", lineHeight: 1.5 },
                },
            },
            MuiAppBar: {
                styleOverrides: {
                    root: ({ theme }) => ({
                        backgroundColor:
                            theme.palette.mode === "dark"
                                ? theme.palette.background.default
                                : palette.paper,
                        color: theme.palette.text.primary,
                        borderBottom: `1px solid ${palette.divider}`,
                        boxShadow: "none",
                    }),
                },
            },
            MuiCard: {
                styleOverrides: {
                    root: {
                        backgroundColor: palette.paper,
                        color: palette.text,
                        border: `1px solid ${palette.divider}`,
                    },
                },
            },
            MuiPaper: {
                styleOverrides: { root: { backgroundImage: "none" } },
            },
            MuiLink: {
                styleOverrides: {
                    root: {
                        color: palette.link,
                        textDecorationColor: palette.link,
                    },
                },
            },
            MuiOutlinedInput: {
                styleOverrides: { root: { backgroundColor: palette.paper } },
            },
            MuiIconButton: {
                styleOverrides: {
                    root: {
                        color: palette.text,
                        "&:hover": { backgroundColor: palette.sidebarHover },
                    },
                },
            },
            MuiChip: {
                styleOverrides: {
                    root: {
                        minHeight: "2rem",
                        ...(mode === "dark"
                            ? {
                                  borderColor: palette.border,
                                  color: palette.text,
                                  backgroundColor: "transparent",
                              }
                            : {}),
                    },
                    label: { fontSize: "1rem", lineHeight: 1.5 },
                },
            },
            MuiListItemButton: {
                styleOverrides: {
                    root: {
                        color: palette.text,
                        "&.Mui-selected": {
                            backgroundColor: palette.sidebarHover,
                            color: palette.text,
                        },
                        "&:hover": { backgroundColor: palette.sidebarHover },
                    },
                },
            },
        },
    };

    return createTheme(themeOptions);
};
