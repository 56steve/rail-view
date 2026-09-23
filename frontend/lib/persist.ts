// Per-device preferences (saved trains/journeys, alerts, layer toggles).
// Storage can be unavailable (private mode, blocked site data), so every
// access is guarded and the app works without it - just without memory.

const PREFIX = "railview:";

export function readStored<T>(key: string, fallback: T, isValid: (value: unknown) => value is T): T {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (raw === null) return fallback;
    const parsed: unknown = JSON.parse(raw);
    return isValid(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

export function writeStored(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Storage full or blocked: preferences just won't survive a reload.
  }
}
