
interface Props {
  aspect: "9:16" | "1:1" | "4:5" | "16:9";
}

const BASE = 90;
const RATIOS: Record<Props["aspect"], { w: number; h: number }> = {
  "9:16": { w: (BASE * 9) / 16, h: BASE },
  "1:1": { w: BASE, h: BASE },
  "4:5": { w: (BASE * 4) / 5, h: BASE },
  "16:9": { w: BASE, h: (BASE * 9) / 16 },
};

export function AspectPreview({ aspect }: Props) {
  const { w, h } = RATIOS[aspect];
  return (
    <div className="flex items-center gap-3 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] px-3 py-2">
      <span className="text-[11px] uppercase tracking-[0.1em] text-[color:var(--text-muted)]">
        Превью кадра
      </span>
      <div
        className="flex shrink-0 items-center justify-center"
        style={{ width: BASE, height: BASE }}
      >
        <div
          aria-hidden="true"
          className="rounded-sm border-2 border-[color:var(--accent-primary)] bg-[color:var(--surface-raised)]"
          style={{ width: `${w}px`, height: `${h}px` }}
        />
      </div>
      <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-primary)]">
        {aspect}
      </span>
    </div>
  );
}
