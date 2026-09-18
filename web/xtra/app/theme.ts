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
    border: "#355367",
    divider: "#29475A",
    link: "#B7F7F5",
    focus: "#FFD89A",
    sidebar: "#0D1F2D",
    sidebarBorder: "#1F3B4E",
    sidebarHover: "#1F3B4E",
    footer: "#0D1F2D",
    envDev: { background: "#5c4a00", text: "#FFF3CD" },
    envStaging: { background: "#0c4a5e", text: "#D1ECF1" },
};

export const applyColorSchemeVariables = (mode: PaletteMode) => {
    const palette = mode === "dark" ? darkPalette : lightPalette;

    if (typeof globalThis.document === "undefined") {
        return;
    }

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
    root.style.setProperty("--ce-aqua-dark", palette.aquaDark);
    root.style.setProperty("--ce-aqua-light", palette.accentSoft);
    root.style.setProperty("--ce-border", palette.border);
    root.style.setProperty("--ce-link", palette.link);
    root.style.setProperty("--ce-focus", palette.focus);
};

export const createAppTheme = (mode: PaletteMode = "light") => {
    const palette = mode === "dark" ? darkPalette : lightPalette;

    const themeOptions: ThemeOptions = {
        typography: {
            fontFamily: "var(--font-geist-sans), Arial, Helvetica, sans-serif",
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
        },
        components: {
            MuiCssBaseline: {
                styleOverrides: {
                    body: {
                        backgroundColor: palette.background,
                        color: palette.text,
                    },
                    a: {
                        color: palette.link,
                    },
                    "*:focus-visible": {
                        outline: `3px solid ${palette.focus}`,
                        outlineOffset: "3px",
                    },
                },
            },
            MuiButton: {
                defaultProps: {
                    disableElevation: true,
                },
                styleOverrides: {
                    root: {
                        borderRadius: 8,
                        fontWeight: 700,
                        textTransform: "none",
                    },
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
            MuiPaper: {
                styleOverrides: {
                    root: {
                        backgroundImage: "none",
                    },
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
            MuiOutlinedInput: {
                styleOverrides: {
                    root: {
                        backgroundColor: palette.paper,
                    },
                },
            },
            MuiLink: {
                styleOverrides: {
                    root: {
                        color: palette.link,
                        textDecorationColor: palette.link,
                    },
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
                        "&:hover": {
                            backgroundColor: palette.sidebarHover,
                        },
                    },
                },
            },
        },
    };

    return createTheme(themeOptions);
};
