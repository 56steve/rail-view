"use client";

import { useEffect, useSyncExternalStore, type RefObject } from "react";
import { useRailView } from "@/lib/store";

const DESKTOP_QUERY = "(min-width: 768px)";
// Sidebar column width plus its outer margin (see RailViewApp).
export const SIDEBAR_INSET_PX = 444;

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(DESKTOP_QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

export function useIsDesktop(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => false,
  );
}

/** Desktop: the sidebar covers the left of the map (and nothing else). */
export function useDesktopInsets(): void {
  const isDesktop = useIsDesktop();
  useEffect(() => {
    useRailView.getState().setViewInsets({ left: isDesktop ? SIDEBAR_INSET_PX : 0, top: 0, bottom: 0 });
  }, [isDesktop]);
}

/**
 * Mobile: report how much of the map a screen's overlay UI covers, so the
 * camera centres and frames content in the clear area between them. `top`
 * covers from the screen top to the element's bottom edge; `bottom` from
 * the element's top edge to the screen bottom (so it includes the tab bar).
 */
export function useMobileInset(side: "top" | "bottom", ref: RefObject<HTMLElement | null>): void {
  const isDesktop = useIsDesktop();
  useEffect(() => {
    const element = ref.current;
    if (isDesktop || !element) return;
    const { setViewInsets } = useRailView.getState();
    const report = () => {
      const rect = element.getBoundingClientRect();
      const covered = side === "top" ? rect.bottom : window.innerHeight - rect.top;
      setViewInsets({ [side]: Math.max(0, Math.round(covered)) });
    };
    const observer = new ResizeObserver(report);
    observer.observe(element);
    window.addEventListener("resize", report);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", report);
      setViewInsets({ [side]: 0 });
    };
  }, [isDesktop, ref, side]);
}
