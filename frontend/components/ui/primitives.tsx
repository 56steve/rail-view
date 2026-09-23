import type { ButtonHTMLAttributes, ReactNode } from "react";
import { delayTone, formatDelay } from "@/lib/format";

export function IconButton({
  label,
  children,
  className = "",
  active = false,
  ...props
}: { label: string; children: ReactNode; active?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`pointer-events-auto flex h-11 w-11 shrink-0 items-center justify-center rounded-full shadow-float transition active:scale-95 ${
        active ? "bg-primary text-white" : "glass text-fg hover:bg-ink-700"
      } ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function PrimaryButton({
  children,
  className = "",
  ...props
}: { children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`flex h-13 w-full items-center justify-center gap-2 rounded-2xl bg-primary text-[15px] font-semibold text-white shadow-[0_10px_30px_-10px_rgb(76_125_255/0.7)] transition hover:bg-primary-strong active:scale-[0.99] disabled:opacity-40 ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

export function LineSwatch({ color, className = "h-2.5 w-2.5" }: { color: string; className?: string }) {
  return <span className={`inline-block shrink-0 rounded-full ${className}`} style={{ backgroundColor: color }} />;
}

const TONE_CLASS = { "on-time": "text-success", late: "text-danger", early: "text-primary" } as const;

export function DelayText({ seconds, className = "" }: { seconds: number; className?: string }) {
  return <span className={`${TONE_CLASS[delayTone(seconds)]} ${className}`}>{formatDelay(seconds)}</span>;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="px-1 text-[15px] font-semibold text-fg">{children}</h2>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border hairline bg-ink-800 ${className}`}>{children}</div>;
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-dashed hairline px-5 py-8 text-center">
      <p className="text-[14px] font-medium text-fg">{title}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-fg-subtle">{body}</p>
    </div>
  );
}
