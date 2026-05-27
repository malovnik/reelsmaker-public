
import type { ApiError, VideoAsset } from "@/lib/api";

export function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-[color:var(--text-muted)]">
        {label}
      </span>
      {children}
    </label>
  );
}

export function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] p-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
        {title}
      </h3>
      {children}
    </div>
  );
}

export function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-[color:var(--text-primary)]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 accent-[color:var(--accent-primary)]"
      />
      {label}
    </label>
  );
}

export function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
      />
    </Field>
  );
}

export function AssetSelect({
  assets,
  value,
  onChange,
}: {
  assets: VideoAsset[];
  value: number | null;
  onChange: (id: number | null) => void;
}) {
  return (
    <select
      value={value === null ? "" : String(value)}
      onChange={(e) => {
        const raw = e.target.value;
        onChange(raw === "" ? null : Number(raw));
      }}
      className="w-full rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
    >
      <option value="">— не использовать —</option>
      {assets.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name} ({a.duration_sec.toFixed(1)} с · {a.width}×{a.height})
        </option>
      ))}
    </select>
  );
}

export function extractDetail(err: ApiError): string {
  if (typeof err.detail === "string") return err.detail;
  if (err.detail && typeof err.detail === "object" && "detail" in err.detail) {
    const d = (err.detail as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    return JSON.stringify(d);
  }
  return JSON.stringify(err.detail);
}
