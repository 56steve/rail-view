"use client";

import { useEffect } from "react";
import { BellRing, X } from "lucide-react";
import { useRailView, type Toast } from "@/lib/store";

const TOAST_MS = 6000;

export function Toasts() {
  const toasts = useRailView((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-50 flex flex-col items-center gap-2 px-4 pt-safe">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} />
      ))}
    </div>
  );
}

function ToastItem({ toast }: { toast: Toast }) {
  const dismiss = useRailView((s) => s.dismissToast);
  useEffect(() => {
    const timer = setTimeout(() => dismiss(toast.id), TOAST_MS);
    return () => clearTimeout(timer);
  }, [dismiss, toast.id]);

  return (
    <div
      role="status"
      className="glass pointer-events-auto animate-rise flex w-full max-w-sm items-start gap-3 rounded-2xl px-4 py-3 shadow-float"
    >
      <BellRing className={`mt-0.5 h-5 w-5 shrink-0 ${toast.tone === "warning" ? "text-warning" : "text-success"}`} />
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-semibold text-fg">{toast.title}</p>
        <p className="mt-0.5 truncate text-[12.5px] text-fg-muted">{toast.body}</p>
      </div>
      <button type="button" aria-label="Dismiss" onClick={() => dismiss(toast.id)} className="text-fg-subtle hover:text-fg">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export function ConnectionBanner() {
  const status = useRailView((s) => s.connectionStatus);
  if (status !== "reconnecting") return null;
  return (
    <div
      role="status"
      className="glass pointer-events-auto flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-[12.5px] text-fg-muted"
    >
      <span className="h-2 w-2 animate-soft-pulse rounded-full bg-warning" />
      Reconnecting — trains show their last known position
    </div>
  );
}
