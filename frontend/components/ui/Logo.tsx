export function LogoMark({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
      <path
        d="M3 20.5c3.2 0 4.3-9 7.5-9s4.2 9 7.5 9 4.2-9 7.5-9c2 0 3 2.4 3.5 4.6"
        stroke="#4C7DFF"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <LogoMark className="h-7 w-7" />
      <span className="text-[19px] font-semibold tracking-[-0.01em] text-fg">RailView</span>
    </div>
  );
}
