import { X } from "lucide-react";
import { useState } from "react";

interface DependencyTagsInputProps {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  helperText?: string;
  disabled?: boolean;
}

const parseDependencyValues = (rawValue: string): string[] =>
  rawValue
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);

export default function DependencyTagsInput({
  values,
  onChange,
  placeholder,
  helperText,
  disabled = false,
}: DependencyTagsInputProps) {
  const [draftValue, setDraftValue] = useState("");

  const appendDependencies = (rawValue: string) => {
    const nextItems = parseDependencyValues(rawValue);
    if (nextItems.length === 0) {
      return false;
    }

    const seen = new Set(values.map((item) => item.toLowerCase()));
    const mergedValues = [...values];
    let changed = false;

    for (const item of nextItems) {
      const normalizedKey = item.toLowerCase();
      if (seen.has(normalizedKey)) {
        continue;
      }
      seen.add(normalizedKey);
      mergedValues.push(item);
      changed = true;
    }

    if (changed) {
      onChange(mergedValues);
    }

    return changed;
  };

  const commitDraftValue = () => {
    if (disabled) {
      return;
    }

    const changed = appendDependencies(draftValue);
    if (changed || draftValue.trim().length > 0) {
      setDraftValue("");
    }
  };

  const handleRemove = (index: number) => {
    if (disabled) {
      return;
    }

    onChange(values.filter((_, currentIndex) => currentIndex !== index));
  };

  return (
    <div className="space-y-2">
      <div className="flex min-h-[46px] flex-wrap items-center gap-2 rounded-xl border border-zinc-200 bg-white/70 px-3 py-2.5 transition-colors focus-within:border-emerald-500 dark:border-zinc-700 dark:bg-zinc-900/50">
        {values.map((value, index) => (
          <span
            key={`${value}-${index}`}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-sm text-emerald-700 dark:text-emerald-300"
          >
            {value}
            {!disabled && (
              <button
                type="button"
                onClick={() => handleRemove(index)}
                className="rounded-sm transition-colors hover:text-emerald-900 dark:hover:text-emerald-100"
                aria-label={`Remove ${value}`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </span>
        ))}
        {!disabled && (
          <input
            type="text"
            value={draftValue}
            onChange={(event) => setDraftValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === ",") {
                event.preventDefault();
                commitDraftValue();
                return;
              }

              if (event.key === "Backspace" && draftValue.length === 0 && values.length > 0) {
                event.preventDefault();
                handleRemove(values.length - 1);
              }
            }}
            onBlur={commitDraftValue}
            onPaste={(event) => {
              const pastedText = event.clipboardData.getData("text");
              if (!/[\n,]/.test(pastedText)) {
                return;
              }
              event.preventDefault();
              appendDependencies(pastedText);
              setDraftValue("");
            }}
            className="min-w-[180px] flex-1 bg-transparent text-sm text-zinc-800 outline-none placeholder:text-zinc-500 dark:text-white dark:placeholder:text-zinc-400"
            placeholder={values.length === 0 ? placeholder : undefined}
          />
        )}
      </div>
      {helperText && (
        <p className="text-xs text-zinc-600 dark:text-zinc-400">{helperText}</p>
      )}
    </div>
  );
}
