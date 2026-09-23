import type { ReactNode } from "react";

/** Full-height scrolling panel used by the list-style tab screens. */
export function PanelScreen({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="pointer-events-auto min-h-0 flex-1 overflow-y-auto bg-ink-950 px-4 pb-6 pt-safe md:rounded-3xl md:border md:hairline md:px-5 md:pt-5 md:shadow-float">
      <header className="pb-4 pt-2">
        <h1 className="text-[24px] font-semibold tracking-[-0.01em] text-fg">{title}</h1>
        {subtitle && <p className="mt-1 text-[13.5px] text-fg-muted">{subtitle}</p>}
      </header>
      {children}
    </div>
  );
}
