import { Slider } from "@/components/ui";
import type { NumericProps } from "./NumberRow";
import { resolveHint } from "./hintAdornment";

/**
 * Ползунок с обязательной подсказкой (Эксперт-студия §2).
 * `hintKey` → триплет what/effect/advise + бейдж из реестра; `hint` — fallback.
 */
export function SliderRow({
  id,
  label,
  hintKey,
  hint,
  value,
  min,
  max,
  step,
  unit,
  disabled,
  onChange,
}: NumericProps) {
  const { inline, adornment, badgeNode } = resolveHint({ hintKey, hint });
  return (
    <Slider
      id={id}
      label={
        <span className="inline-flex items-center gap-2">
          {label}
          {badgeNode}
        </span>
      }
      hint={inline}
      adornment={adornment}
      value={value}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      formatValue={(v) => (unit ? `${v} ${unit}` : v)}
      onValueChange={onChange}
    />
  );
}
