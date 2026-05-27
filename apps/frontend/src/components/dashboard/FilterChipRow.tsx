
import type { VisionProfile } from "@/lib/api";

export type ProfileFilter = VisionProfile | "all";

interface Props {
  value: ProfileFilter;
  onChange: (next: ProfileFilter) => void;
  counts: Record<ProfileFilter, number>;
}

const CHIPS: Array<{
  key: ProfileFilter;
  label: string;
  color: string | null;
}> = [
  { key: "all", label: "Все", color: null },
  {
    key: "talking_head",
    label: "Говорящая голова",
    color: "var(--profile-talking-head)",
  },
  { key: "fashion", label: "Фэшн", color: "var(--profile-fashion)" },
  { key: "travel", label: "Трэвел", color: "var(--profile-travel)" },
  {
    key: "screencast",
    label: "Скринкаст",
    color: "var(--profile-screencast)",
  },
  { key: "custom", label: "Своя настройка", color: "var(--profile-custom)" },
];

export function FilterChipRow({ value, onChange, counts }: Props) {
  return (
    <div className="-mx-1 flex flex-wrap gap-1.5" role="tablist">
      {CHIPS.map((chip) => {
        const active = value === chip.key;
        const count = counts[chip.key] ?? 0;
        return (
          <button
            key={chip.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(chip.key)}
            className={[
              "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors duration-150",
              active
                ? "border-[color:var(--text-primary)] bg-[color:var(--text-primary)] text-[color:var(--text-inverse)]"
                : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]",
            ].join(" ")}
          >
            {chip.color ? (
              <span
                aria-hidden="true"
                className="size-1.5 rounded-full"
                style={{ backgroundColor: active ? "currentColor" : chip.color }}
              />
            ) : null}
            <span>{chip.label}</span>
            <span
              className={
                active
                  ? "rounded-full bg-white/20 px-1.5 text-[10px] font-mono"
                  : "rounded-full bg-[color:var(--surface-sunken)] px-1.5 text-[10px] font-mono text-[color:var(--text-muted)]"
              }
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
