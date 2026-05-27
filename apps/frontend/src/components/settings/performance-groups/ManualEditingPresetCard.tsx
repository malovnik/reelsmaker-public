
interface Props {
  onApply: () => void;
}

export function ManualEditingPresetCard({ onApply }: Props) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-[color:var(--line-soft)] bg-[color:var(--ink-3)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-[color:var(--text-primary)]">
            Пресет «Ручной монтаж»
          </h3>
          <p className="mt-1 text-xs text-[color:var(--text-muted)]">
            Включает детектор цокания, распознавание вдоха,
            пунктуационные паузы, контекстный J/L-chooser и адаптивное
            выравнивание громкости с research-дефолтами. Одна кнопка —
            монтаж как от человека.
          </p>
        </div>
        <button
          type="button"
          onClick={onApply}
          className="shrink-0 rounded-md bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-violet-700"
        >
          Применить
        </button>
      </div>
    </div>
  );
}
