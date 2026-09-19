import {
    createTheme,
    type PaletteMode,
    type ThemeOptions,
} from "@mui/material/styles";

export const lightPalette = {
    background: "#FFFFFF",
    paper: "#FFFFFF",
    surface: "#F7FAFC",
    text: "#0A2942",
    textSecondary: "#314A5E",
    primary: "#0A2942",
    primaryContrast: "#FFFFFF",
    secondary: "#005D5B",
    secondaryContrast: "#FFFFFF",
    accent: "#005D5B",
    aquaDark: "#005D5B",
    accentSoft: "#D8F4F3",
    border: "#7B8B98",
    divider: "#C4CDD4",
    link: "#063C68",
    focus: "#6A3D12",
    actionAquaBg: "#005D5B",
    actionAquaText: "#FFFFFF",
    actionBlueBg: "#0A2942",
    actionBlueText: "#FFFFFF",
    actionBrownBg: "#6A3D12",
    actionBrownText: "#FFFFFF",
    panelStrongBg: "#005D5B",
    panelStrongText: "#FFFFFF",
    cardSelectedBg: "#E8EEF2",
    sidebar: "#F7FBFA",
    sidebarBorder: "#C4CDD4",
    sidebarHover: "#E8EEF2",
    footer: "#F0F0F0",
    envDev: { background: "#FFF3CD", text: "#000000" },
    envStaging: { background: "#D1ECF1", text: "#000000" },
};

export const darkPalette = {
    background: "#07131D",
    paper: "#102332",
    surface: "#172F41",
    text: "#FFFFFF",
    textSecondary: "#E7EEF3",
    primary: "#FFFFFF",
    primaryContrast: "#07131D",
    secondary: "#99F3F0",
    secondaryContrast: "#07131D",
    accent: "#99F3F0",
    aquaDark: "#005D5B",
    accentSoft: "#143B47",
    border: "#F1F6F9",
    divider: "#D7E3EA",
    link: "#B7F7F5",
    focus: "#FFD89A",
    actionAquaBg: "#005D5B",
    actionAquaText: "#FFFFFF",
    actionBlueBg: "#FFFFFF",
    actionBlueText: "#07131D",
    actionBrownBg: "#FFD89A",
    actionBrownText: "#07131D",
    panelStrongBg: "#005D5B",
    panelStrongText: "#FFFFFF",
    cardSelectedBg: "#1F3B4E",
    sidebar: "#0D1F2D",
    sidebarBorder: "#1F3B4E",
    sidebarHover: "#1F3B4E",
    footer: "#0D1F2D",
    envDev: { background: "#5c4a00", text: "#FFF3CD" },
    envStaging: { background: "#0c4a5e", text: "#D1ECF1" },
};

export const applyColorSchemeVariables = (mode: PaletteMode) => {
    const palette = mode === "dark" ? darkPalette : lightPalette;

    if (typeof globalThis.document === "undefined") return;

    const root = globalThis.document.documentElement;
    root.dataset.theme = mode;
    root.classList.toggle("dark", mode === "dark");
    root.style.colorScheme = mode;
    root.style.setProperty("--background", palette.background);
    root.style.setProperty("--foreground", palette.text);
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
                default: palette.text,
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
            MuiChip: {
                styleOverrides: {
                    root: { minHeight: "2rem" },
                    label: { fontSize: "1rem", lineHeight: 1.5 },
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
                                : theme.palette.primary.main,
                        color:
                            theme.palette.mode === "dark"
                                ? theme.palette.text.primary
                                : theme.palette.primary.contrastText,
                        borderBottom: "none",
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
