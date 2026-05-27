
interface Props {
  onApply: () => void;
}

export function ManualEditingPresetCard({ onApply }: Props) {
  return (
    <div className="flex flex-col gap-3 rounded-none border border-[color:var(--line)] bg-[color:var(--ink-3)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-[color:var(--paper)]">
            Пресет «Ручной монтаж»
          </h3>
          <p className="mt-1 text-xs text-[color:var(--mute)]">
            Включает детектор цокания, распознавание вдоха,
            пунктуационные паузы, контекстный J/L-chooser и адаптивное
            выравнивание громкости с research-дефолтами. Одна кнопка —
            монтаж как от человека.
          </p>
        </div>
        <button
          type="button"
          onClick={onApply}
          className="shrink-0 rounded-none border border-[color:var(--gold)] px-3 py-1.5 text-xs font-semibold text-[color:var(--gold)] transition-colors hover:bg-[color:var(--gold)] hover:text-[color:var(--ink)]"
        >
          Применить
        </button>
      </div>
    </div>
  );
}
