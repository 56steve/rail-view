import { ConnectionBadge } from "./ConnectionBadge";
import { ViewModeToggle } from "./ViewModeToggle";

export function TopBar() {
  return (
    <div className="pointer-events-none flex items-center justify-between px-4 pt-4 sm:px-6 sm:pt-6">
      <div className="pointer-events-auto flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-teal-400 shadow-[0_0_10px_2px_rgba(43,217,192,0.6)]" />
        <span className="text-sm font-semibold tracking-wide text-white">RailPulse</span>
      </div>
      <div className="flex items-center gap-2">
        <ViewModeToggle />
        <ConnectionBadge />
      </div>
    </div>
  );
}
