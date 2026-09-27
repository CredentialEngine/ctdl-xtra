import "@mui/material/styles";

declare module "@mui/material/styles" {
    interface Palette {
        blueDark: string;
        brown: string;
        greyDark: string;
        greyLight: string;
        aquaDark: string;
        aquaLight: string;
        white: string;
        selected: string;
        sidebar: {
            background: string;
            border: string;
            hoverBackground: string;
        };
        envChip: {
            development: { background: string; text: string };
            staging: { background: string; text: string };
        };
        footer: {
            background: string;
        };
        link: {
            default: string;
            hover: string;
        };
    }

    interface PaletteOptions {
        blueDark?: string;
        brown?: string;
        greyDark?: string;
        greyLight?: string;
        aquaDark?: string;
        aquaLight?: string;
        white?: string;
        selected?: string;
        sidebar?: {
            background?: string;
            border?: string;
            hoverBackground?: string;
        };
        envChip?: {
            development?: { background?: string; text?: string };
            staging?: { background?: string; text?: string };
        };
        footer?: {
            background?: string;
        };
        link?: {
            default?: string;
            hover?: string;
        };
    }
}
