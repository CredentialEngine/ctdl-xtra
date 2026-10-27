// Light / dark theme. The choice is remembered in this browser; with no choice yet, it follows the system setting.
import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "studio.theme";

export function storedTheme(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export function systemTheme(): Theme {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(t: Theme): void {
  document.documentElement.dataset.theme = t;
  document.documentElement.style.colorScheme = t;
}

/** Set the theme before React renders, so the page never flashes light. */
export function initTheme(): void {
  applyTheme(storedTheme() ?? systemTheme());
}

export function ThemeButton() {
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? systemTheme());
  useEffect(() => applyTheme(theme), [theme]);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button className="theme-btn" onClick={() => { setTheme(next); try { localStorage.setItem(KEY, next); } catch { /* private mode */ } }}
      title={`Switch to ${next} mode`} aria-label={`Switch to ${next} mode`} data-tour="theme">
      {theme === "dark"
        ? <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
            <circle cx="8" cy="8" r="3" /><path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" /></svg>
        : <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true">
            <path d="M13.5 9.6A5.6 5.6 0 0 1 6.4 2.5a5.6 5.6 0 1 0 7.1 7.1Z" /></svg>}
      <span>{theme === "dark" ? "Light" : "Dark"}</span>
    </button>
  );
}
