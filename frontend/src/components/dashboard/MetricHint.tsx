import React from "react";
import { Info } from "lucide-react";

interface MetricHintProps {
  text: string;
}

export const MetricHint: React.FC<MetricHintProps> = ({ text }) => {
  return (
    <span className="relative inline-flex z-[70]">
      <button
        type="button"
        className="peer inline-flex items-center justify-center rounded-full text-zinc-400 hover:text-zinc-600 dark:text-zinc-500 dark:hover:text-zinc-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/70"
        aria-label={text}
        title={text}
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-[80] mt-2 w-64 rounded-lg border border-zinc-200/80 bg-white/95 p-2 text-[11px] leading-4 text-zinc-600 opacity-0 shadow-xl backdrop-blur-sm transition-opacity duration-150 peer-hover:opacity-100 peer-focus-visible:opacity-100 dark:border-zinc-700/80 dark:bg-zinc-900/95 dark:text-zinc-300"
      >
        {text}
      </span>
    </span>
  );
};
