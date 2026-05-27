
import { Field } from "./shared";

interface Props {
  name: string;
  isDefault: boolean;
  onNameChange: (value: string) => void;
  onIsDefaultChange: (value: boolean) => void;
}

export function PresetIdentitySection({
  name,
  isDefault,
  onNameChange,
  onIsDefaultChange,
}: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Field label="Название">
        <input
          type="text"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          className="w-full rounded-none border border-[color:var(--line)] bg-[color:var(--ink)] px-3 py-2 text-sm text-[color:var(--paper)] outline-none focus:border-[color:var(--gold)]"
        />
      </Field>
      <Field label="По умолчанию">
        <label className="flex h-9 cursor-pointer items-center gap-2 text-sm text-[color:var(--mute-2)]">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => onIsDefaultChange(e.target.checked)}
            className="size-4 accent-[color:var(--gold)]"
          />
          Применять к новым нарезкам
        </label>
      </Field>
    </div>
  );
}
