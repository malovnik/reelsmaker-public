
import {
  DEFAULT_SUBTITLE_STYLE,
  FONT_WEIGHTS,
  SUBTITLE_ANCHORS,
  SUBTITLE_POSITION_MODES,
  SUBTITLE_WRAP_MODES,
  type FontWeight,
  type SubtitleAnchor,
  type SubtitlePositionMode,
  type SubtitleStyleConfig,
  type SubtitleWrapMode,
} from "@/lib/api";

/**
 * Controlled-форма редактор `SubtitleStyleConfig`.
 *
 * Диапазоны смещения зависят от положения и режима масштабирования:
 *   - заполнение (fill), сверху/снизу: 0–300 px
 *   - вписывание (fit), сверху/снизу: 1–150 px (от края видео)
 *   - по центру + fill: 0–300 (сдвиг от центра)
 *   - по центру + fit: смещение не применяется → слайдер заблокирован
 */

interface FavouriteFonts {
  favourites: string[];
  onToggle: (font: string) => void;
}

interface Props {
  value: SubtitleStyleConfig;
  onChange: (next: SubtitleStyleConfig) => void;
  fitMode: "fill" | "fit";
  onFitModeChange?: (next: "fill" | "fit") => void;
  aspect: string;
  onAspectChange?: (next: string) => void;
  fonts: string[];
  favourites?: FavouriteFonts;
  aspectOptions?: string[];
}

export function SubtitleStyleEditor({
  value,
  onChange,
  fitMode,
  onFitModeChange,
  aspect,
  onAspectChange,
  fonts,
  favourites,
  aspectOptions = ["9:16", "16:9", "1:1", "4:5"],
}: Props) {
  const set = <K extends keyof SubtitleStyleConfig>(
    key: K,
    next: SubtitleStyleConfig[K],
  ) => {
    onChange({ ...value, [key]: next });
  };

  const offsetRange = getOffsetRange(value.anchor, fitMode);
  const offsetDisabled = value.anchor === "center" && fitMode === "fit";

  const sortedFonts = sortFonts(fonts, favourites?.favourites ?? []);

  return (
    <div className="flex flex-col gap-6">
      {onFitModeChange && onAspectChange && (
        <Section title="Вид превью">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Формат видео">
              <Select
                value={aspect}
                onChange={(v) => onAspectChange(v)}
                options={aspectOptions.map((a) => ({ value: a, label: a }))}
              />
            </Field>
            <Field label="Как вписывать">
              <SegmentedControl
                value={fitMode}
                options={[
                  { value: "fill", label: "заполнить" },
                  { value: "fit", label: "вписать" },
                ]}
                onChange={(v) => onFitModeChange(v as "fill" | "fit")}
              />
            </Field>
          </div>
        </Section>
      )}

      <Section title="Положение">
        <Field label="Режим позиционирования">
          <SegmentedControl
            value={value.position_mode}
            options={SUBTITLE_POSITION_MODES.map((m) => ({
              value: m,
              label: m === "anchor" ? "Якорь + смещение" : "Свободно (drag)",
            }))}
            onChange={(v) => set("position_mode", v as SubtitlePositionMode)}
          />
        </Field>

        {value.position_mode === "anchor" && (
          <>
            <Field label="Где размещать текст">
              <SegmentedControl
                value={value.anchor}
                options={SUBTITLE_ANCHORS.map((a) => ({
                  value: a,
                  label: anchorLabel(a),
                }))}
                onChange={(v) => {
                  const nextAnchor = v as SubtitleAnchor;
                  const nextRange = getOffsetRange(nextAnchor, fitMode);
                  const clamped = Math.max(
                    nextRange.min,
                    Math.min(nextRange.max, value.offset_px),
                  );
                  onChange({ ...value, anchor: nextAnchor, offset_px: clamped });
                }}
              />
            </Field>
            <Field
              label={`Смещение от края (${offsetRange.min}–${offsetRange.max} пикс)`}
              hint={
                offsetDisabled
                  ? "Для центрального размещения смещение не применяется."
                  : fitMode === "fit"
                    ? "Субтитры смещаются внутрь, от края чёрных полос видео."
                    : "Субтитры смещаются от выбранного края кадра."
              }
            >
              <NumberSlider
                value={value.offset_px}
                min={offsetRange.min}
                max={offsetRange.max}
                step={1}
                disabled={offsetDisabled}
                onChange={(v) => set("offset_px", v)}
              />
            </Field>
          </>
        )}

        {value.position_mode === "free" && (
          <>
            <Field
              label="Центр X (% от ширины)"
              hint="Перетащи текст на превью или задай значение вручную."
            >
              <NumberSlider
                value={Math.round(value.free_x_pct)}
                min={0}
                max={100}
                step={1}
                onChange={(v) => set("free_x_pct", v)}
              />
            </Field>
            <Field label="Центр Y (% от высоты)">
              <NumberSlider
                value={Math.round(value.free_y_pct)}
                min={0}
                max={100}
                step={1}
                onChange={(v) => set("free_y_pct", v)}
              />
            </Field>
            <Field
              label="Не вылезать за Instagram safe zones"
              hint="Учитывает UI-элементы IG Reels (шапка, иконки, подпись)."
            >
              <label className="flex cursor-pointer items-center gap-2 text-sm text-[color:var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={value.clamp_to_safe_zone}
                  onChange={(e) => set("clamp_to_safe_zone", e.target.checked)}
                  className="size-4 accent-[color:var(--accent-primary)]"
                />
                Обрезать позицию по safe-zone границам
              </label>
            </Field>
          </>
        )}
      </Section>

      <Section title="Разбиение на субтитры">
        <Field label="Режим нарезки текста">
          <SegmentedControl
            value={value.wrap_mode}
            options={SUBTITLE_WRAP_MODES.map((m) => ({
              value: m,
              label: wrapModeLabel(m),
            }))}
            onChange={(v) => set("wrap_mode", v as SubtitleWrapMode)}
          />
        </Field>
        <Field
          label="Максимум строк в одном субтитре"
          hint="1 — одна строка, разбивает длинные фразы; 3 — максимум три."
        >
          <SegmentedControl
            value={String(value.max_lines)}
            options={[
              { value: "1", label: "1" },
              { value: "2", label: "2" },
              { value: "3", label: "3" },
            ]}
            onChange={(v) => set("max_lines", Number(v) as 1 | 2 | 3)}
          />
        </Field>
        {value.wrap_mode === "chars" && (
          <Field
            label={`Максимум знаков в строке (${value.max_chars_per_line})`}
            hint="10–60. Оптимум для 9:16 — 28–32."
          >
            <NumberSlider
              value={value.max_chars_per_line}
              min={10}
              max={60}
              step={1}
              onChange={(v) => set("max_chars_per_line", v)}
            />
          </Field>
        )}
      </Section>

      <Section title="Шрифт">
        <Field label="Название шрифта">
          <FontPicker
            value={value.font}
            fonts={sortedFonts}
            favourites={favourites?.favourites ?? []}
            onChange={(v) => set("font", v)}
            onToggleFavourite={favourites?.onToggle}
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={`Размер (${value.size} пикс)`}>
            <NumberSlider
              value={value.size}
              min={24}
              max={128}
              step={2}
              onChange={(v) => set("size", v)}
            />
          </Field>
          <Field label="Насыщенность">
            <SegmentedControl
              value={value.weight}
              options={FONT_WEIGHTS.map((w) => ({
                value: w,
                label: weightLabel(w),
              }))}
              onChange={(v) => set("weight", v as FontWeight)}
            />
          </Field>
        </div>
        <Field label="">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-[color:var(--text-secondary)]">
            <input
              type="checkbox"
              checked={value.italic}
              onChange={(e) => set("italic", e.target.checked)}
              className="size-4 accent-[color:var(--accent-primary)]"
            />
            Курсив
          </label>
        </Field>
      </Section>

      <Section title="Цвет и прозрачность">
        <Field label="Основной цвет текста">
          <ColorWithOpacity
            color={value.primary_color}
            opacity={value.text_opacity}
            onColorChange={(v) => set("primary_color", v)}
            onOpacityChange={(v) => set("text_opacity", v)}
          />
        </Field>
      </Section>

      <Section title="Обводка">
        <Field label={`Толщина (${value.outline_width.toFixed(1)} пикс)`}>
          <NumberSlider
            value={value.outline_width}
            min={0}
            max={8}
            step={0.5}
            onChange={(v) => set("outline_width", v)}
          />
        </Field>
        <Field label="Цвет обводки">
          <ColorPicker
            value={value.outline_color}
            onChange={(v) => set("outline_color", v)}
          />
        </Field>
      </Section>

      <Section title="Тень">
        <Field label={`Размер тени (${value.shadow_width.toFixed(1)} пикс)`}>
          <NumberSlider
            value={value.shadow_width}
            min={0}
            max={6}
            step={0.5}
            onChange={(v) => set("shadow_width", v)}
          />
        </Field>
        <Field label="Цвет и прозрачность">
          <ColorWithOpacity
            color={value.shadow_color}
            opacity={value.shadow_opacity}
            onColorChange={(v) => set("shadow_color", v)}
            onOpacityChange={(v) => set("shadow_opacity", v)}
          />
        </Field>
      </Section>

      <Section title="Подложка под текстом">
        <Field label="">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-[color:var(--text-secondary)]">
            <input
              type="checkbox"
              checked={value.background}
              onChange={(e) => set("background", e.target.checked)}
              className="size-4 accent-[color:var(--accent-primary)]"
            />
            Добавить подложку
          </label>
        </Field>
        {value.background && (
          <>
            <Field label="Цвет и прозрачность">
              <ColorWithOpacity
                color={value.background_color}
                opacity={value.background_opacity}
                onColorChange={(v) => set("background_color", v)}
                onOpacityChange={(v) => set("background_opacity", v)}
              />
            </Field>
            <Field
              label={`Внутренний отступ (${value.background_padding} пикс)`}
              hint="При включённой подложке тень автоматически отключается — подложка заменяет её."
            >
              <NumberSlider
                value={value.background_padding}
                min={0}
                max={64}
                step={1}
                onChange={(v) => set("background_padding", v)}
              />
            </Field>
          </>
        )}
      </Section>

      <button
        type="button"
        onClick={() => onChange({ ...DEFAULT_SUBTITLE_STYLE })}
        className="self-start rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1.5 text-xs text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]"
      >
        Вернуть настройки по умолчанию
      </button>
    </div>
  );
}

// ---------- helpers ----------

function getOffsetRange(
  anchor: SubtitleAnchor,
  fitMode: "fill" | "fit",
): { min: number; max: number } {
  if (anchor === "center") return { min: 0, max: 300 };
  if (fitMode === "fit") return { min: 1, max: 150 };
  return { min: 0, max: 300 };
}

function wrapModeLabel(m: SubtitleWrapMode): string {
  if (m === "chars") return "По знакам";
  if (m === "sentence") return "По фразе";
  return "По одному слову";
}

function anchorLabel(a: SubtitleAnchor): string {
  return a === "top" ? "сверху" : a === "center" ? "по центру" : "снизу";
}

function weightLabel(w: FontWeight): string {
  return w === "bold" ? "жирный" : w === "medium" ? "средний" : "обычный";
}

function sortFonts(fonts: string[], favourites: string[]): string[] {
  const favSet = new Set(favourites);
  const fav = fonts.filter((f) => favSet.has(f));
  const rest = fonts.filter((f) => !favSet.has(f));
  return [...fav, ...rest];
}

// ---------- primitive UI ----------

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <h4 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
        {title}
      </h4>
      <div className="flex flex-col gap-3">{children}</div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-[11px] font-medium uppercase tracking-[0.1em] text-[color:var(--text-muted)]">
          {label}
        </label>
      )}
      {children}
      {hint && (
        <p className="text-[11px] text-[color:var(--text-muted)]">{hint}</p>
      )}
    </div>
  );
}

function SegmentedControl<V extends string>({
  value,
  options,
  onChange,
}: {
  value: V;
  options: { value: V; label: string }[];
  onChange: (v: V) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] p-1">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              active
                ? "bg-[color:var(--surface-raised)] text-[color:var(--text-primary)] shadow-[var(--shadow-xs)]"
                : "text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function Select<V extends string>({
  value,
  options,
  onChange,
}: {
  value: V;
  options: { value: V; label: string }[];
  onChange: (v: V) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as V)}
      className="w-full rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function NumberSlider({
  value,
  min,
  max,
  step = 1,
  disabled = false,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 accent-[color:var(--accent-primary)] disabled:opacity-40"
      />
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(e) => {
          const raw = Number(e.target.value);
          if (!Number.isFinite(raw)) return;
          onChange(Math.max(min, Math.min(max, raw)));
        }}
        className="w-20 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 py-1 text-right font-mono text-xs text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)] disabled:opacity-40"
      />
    </div>
  );
}

function ColorPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        className="size-9 cursor-pointer rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => {
          const next = e.target.value.toUpperCase();
          if (/^#[0-9A-F]{0,6}$/.test(next)) onChange(next);
        }}
        className="w-24 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 py-1 font-mono text-xs text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
      />
    </div>
  );
}

function ColorWithOpacity({
  color,
  opacity,
  onColorChange,
  onOpacityChange,
}: {
  color: string;
  opacity: number;
  onColorChange: (v: string) => void;
  onOpacityChange: (v: number) => void;
}) {
  return (
    <div className="grid grid-cols-[auto_1fr] items-center gap-3">
      <ColorPicker value={color} onChange={onColorChange} />
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-[color:var(--text-muted)]">
          прозрачность
        </span>
        <NumberSlider
          value={opacity}
          min={0}
          max={100}
          step={1}
          onChange={onOpacityChange}
        />
      </div>
    </div>
  );
}

function FontPicker({
  value,
  fonts,
  favourites,
  onChange,
  onToggleFavourite,
}: {
  value: string;
  fonts: string[];
  favourites: string[];
  onChange: (v: string) => void;
  onToggleFavourite?: (font: string) => void;
}) {
  const favSet = new Set(favourites);
  const datalistId = "subtitle-fonts";
  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        list={datalistId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Начни печатать название шрифта…"
        className="flex-1 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 text-sm text-[color:var(--text-primary)] outline-none focus:border-[color:var(--accent-primary)]"
        style={{ fontFamily: `'${value}', sans-serif` }}
      />
      <datalist id={datalistId}>
        {fonts.map((f) => (
          <option key={f} value={f}>
            {favSet.has(f) ? `★ ${f}` : f}
          </option>
        ))}
      </datalist>
      {onToggleFavourite && (
        <button
          type="button"
          onClick={() => onToggleFavourite(value)}
          title={favSet.has(value) ? "Убрать из избранных" : "В избранные"}
          className={`rounded-lg border px-2 py-2 text-sm transition-colors ${
            favSet.has(value)
              ? "border-[color:var(--warning)]/60 bg-[color:var(--warning)]/10 text-[color:var(--warning)]"
              : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-muted)] hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)]"
          }`}
        >
          ★
        </button>
      )}
    </div>
  );
}
