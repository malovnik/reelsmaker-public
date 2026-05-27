import { Switch } from "@/components/ui";
import { resolveHint, type HintSource } from "./hintAdornment";

export interface SwitchRowProps extends HintSource {
  id: string;
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}

/**
 * Тоггл с обязательной подсказкой (Эксперт-студия §2).
 * `hintKey` подтягивает триплет what/effect/advise + honesty-бейдж из реестра;
 * `hint`-строка остаётся fallback'ом для обратной совместимости.
 */
export function SwitchRow({
  id,
  label,
  hintKey,
  hint,
  checked,
  disabled,
  onChange,
}: SwitchRowProps) {
  const { inline, adornment, badgeNode } = resolveHint({ hintKey, hint });
  return (
    <Switch
      id={id}
      label={
        <span className="inline-flex items-center gap-2">
          {label}
          {badgeNode}
        </span>
      }
      hint={inline}
      adornment={adornment}
      checked={checked}
      disabled={disabled}
      onCheckedChange={onChange}
    />
  );
}
