import "@mui/material/styles";

declare module "@mui/material/styles" {
    interface Palette {
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
