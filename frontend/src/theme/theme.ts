import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

/** localStorage key. The same key is read by the inline script in index.html. */
export const THEME_STORAGE_KEY = "lab-booking-theme";

const darkQuery = "(prefers-color-scheme: dark)";

function readStoredTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // storage blocked (private mode): fall back to the device setting
  }
}

function systemTheme(): Theme {
  return window.matchMedia(darkQuery).matches ? "dark" : "light";
}

function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
}

const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

function getTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

/** Saves the user's choice and applies it. */
export function setTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // The choice still applies for this visit; it just can't be remembered.
  }
  applyTheme(theme);
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);

  // With no saved choice, follow the device when its setting changes.
  const media = window.matchMedia(darkQuery);
  const onSystemChange = () => {
    if (readStoredTheme() === null) {
      applyTheme(systemTheme());
      notify();
    }
  };
  media.addEventListener("change", onSystemChange);

  // Another tab changed the saved choice.
  const onStorage = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY) {
      applyTheme(readStoredTheme() ?? systemTheme());
      notify();
    }
  };
  window.addEventListener("storage", onStorage);

  return () => {
    listeners.delete(listener);
    media.removeEventListener("change", onSystemChange);
    window.removeEventListener("storage", onStorage);
  };
}

/** The current theme and a function that switches to the other one. */
export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const theme = useSyncExternalStore(subscribe, getTheme, () => "light" as Theme);
  return { theme, toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark") };
}
