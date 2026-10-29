import { Sparkle } from "lucide-react";
import type { ReactNode } from "react";

/** Dark ink card, reserved for agent messages (design.md, Critic note). */
export function AgentMessage({ headline, children }: { headline: string; children: ReactNode }) {
  return (
    <div role="status" className="flex gap-3.5 rounded-card bg-ink px-6 py-5 text-surface animate-fade-in">
      <Sparkle size={22} className="mt-0.5 shrink-0 text-lime" aria-hidden />
      <div>
        <p className="font-semibold">{headline}</p>
        <p className="mt-0.5 text-sm text-[#DAD9CC]">{children}</p>
      </div>
    </div>
  );
}
