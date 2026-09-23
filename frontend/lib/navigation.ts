// Screen navigation backed by browser history, so the hardware/browser
// back button (and the app's own back buttons) behave like a native app:
// every pushed screen is a history entry, and going back is always
// `history.back()` so the store and the browser never disagree.

import { useRailView, type Screen, type TabName } from "./store";

export function navigate(screen: Screen): void {
  useRailView.getState().push(screen);
  window.history.pushState({ railview: useRailView.getState().stack.length }, "");
}

export function navigateBack(): void {
  if (useRailView.getState().stack.length > 1) window.history.back();
}

export function openTab(tab: TabName): void {
  useRailView.getState().openTab(tab);
}

export function handlePopState(): void {
  useRailView.getState().pop();
}
