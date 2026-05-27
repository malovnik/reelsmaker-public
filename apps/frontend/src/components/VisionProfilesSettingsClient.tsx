
import { useMemo, useState } from "react";
import {
  AGENT_NAMES,
  api,
  type AgentName,
  type ProfileMaskRead,
  type VisionProfile,
  type VisionProfileOverride,
} from "@/lib/api";
import { useToast } from "@/contexts/ToastContext";

interface Props {
  initial: ProfileMaskRead[];
}

const PROFILE_LABEL: Record<VisionProfile, string> = {
  talking_head: "Говорящая голова",
  fashion: "Фэшн и стиль",
  travel: "Путешествия",
  screencast: "Скринкаст",
  custom: "Своя настройка",
};

const PROFILE_SHORT: Record<VisionProfile, string> = {
  talking_head: "Подкасты, интервью, выступления",
  fashion: "Показы, lookbook, beauty",
  travel: "Приключения, природа, город",
  screencast: "Туториалы, демо интерфейса",
  custom: "Нестандартные сценарии",
};

const PROFILE_EXPLAIN: Record<VisionProfile, string> = {
  talking_head:
    "Ставка на речь и смысл: все шесть агентов анализа работают, история важнее картинки.",
  fashion:
    "Картинка важнее текста. Агенты по шуткам и тезисам выключены — в показе их обычно нет. Кадр жёстко держит человека между планами.",
  travel:
    "Минимум речи, максимум визуала. Плавная композиция для панорам и пейзажей — без резких рывков кадра.",
  screencast:
    "Речь пояснительная, шутки бессмысленны. Баланс ровный, агенты говорят о тезисах и иронии при наличии.",
  custom: "По умолчанию — как «говорящая голова». Настраивай под свою задачу.",
};

const AGENT_LABEL: Record<AgentName, string> = {
  hook_hunter: "Крючки в начале",
  emotional_peak_finder: "Эмоциональные пики",
  humor_specialist: "Шутки и смех",
  dramatic_irony_scanner: "Ирония и противоречия",
  thesis_extractor: "Главные тезисы",
  motif_tracker: "Повторяющиеся мотивы",
};

const AGENT_HINT: Record<AgentName, string> = {
  hook_hunter: "Ищет сильные первые фразы и цепкие вопросы.",
  emotional_peak_finder: "Находит моменты, где спикер реагирует сильнее обычного.",
  humor_specialist: "Отмечает места со смехом, иронией, панчем.",
  dramatic_irony_scanner:
    "Ловит противоречия — когда спикер говорит одно, а подразумевает другое.",
  thesis_extractor: "Вытягивает ключевые мысли и формулировки-чеканки.",
  motif_tracker: "Следит за тем, что спикер повторяет — это его болевые темы.",
};

interface FormState {
  enabled_agents: Set<AgentName>;
  story_weight: number;
  dead_zone_norm: number;
  ema_alpha: number;
  rule_of_thirds_y_shift: number;
}

function maskToForm(mask: ProfileMaskRead): FormState {
  return {
    enabled_agents: new Set(mask.enabled_agents),
    story_weight: mask.story_weight,
    dead_zone_norm: mask.dead_zone_norm,
    ema_alpha: mask.ema_alpha,
    rule_of_thirds_y_shift: mask.rule_of_thirds_y_shift,
  };
}

function formToPayload(form: FormState): VisionProfileOverride {
  const agents = AGENT_NAMES.filter((a) => form.enabled_agents.has(a));
  const story = Math.round(form.story_weight * 1000) / 1000;
  const visual = Math.round((1 - story) * 1000) / 1000;
  return {
    enabled_agents: agents,
    story_weight: story,
    visual_weight: visual,
    dead_zone_norm: form.dead_zone_norm,
    ema_alpha: form.ema_alpha,
    rule_of_thirds_y_shift: form.rule_of_thirds_y_shift,
  };
}

export function VisionProfilesSettingsClient({ initial }: Props) {
  const [profiles, setProfiles] = useState<ProfileMaskRead[]>(initial);

  if (profiles.length === 0) {
    return (
      <div className="surface-card border-dashed p-6 text-sm text-[color:var(--text-muted)]">
        Не получилось загрузить профили. Проверь, что сервер запущен
        (`./run.sh`), и обнови страницу.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {profiles.map((mask) => (
        <ProfileCard
          key={mask.profile}
          mask={mask}
          onUpdated={(updated) =>
            setProfiles((prev) =>
              prev.map((p) => (p.profile === updated.profile ? updated : p)),
            )
          }
        />
      ))}
    </div>
  );
}

interface CardProps {
  mask: ProfileMaskRead;
  onUpdated: (next: ProfileMaskRead) => void;
}

function ProfileCard({ mask, onUpdated }: CardProps) {
  const toast = useToast();
  const [expanded, setExpanded] = useState(false);
  const [form, setForm] = useState<FormState>(() => maskToForm(mask));
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<
    { kind: "ok" | "error"; message: string } | null
  >(null);

  const initialForm = useMemo(() => maskToForm(mask), [mask]);
  const dirty = useMemo(() => !formsEqual(form, initialForm), [form, initialForm]);

  const updateAgents = (agent: AgentName, checked: boolean) => {
    setForm((prev) => {
      const next = new Set(prev.enabled_agents);
      if (checked) next.add(agent);
      else next.delete(agent);
      return { ...prev, enabled_agents: next };
    });
  };

  const save = async () => {
    if (form.enabled_agents.size === 0) {
      setFlash({
        kind: "error",
        message: "Оставь хотя бы один пункт анализа",
      });
      return;
    }
    setSaving(true);
    setFlash(null);
    try {
      const updated = await api.updateVisionProfile(
        mask.profile,
        formToPayload(form),
      );
      onUpdated(updated);
      setForm(maskToForm(updated));
      setFlash({ kind: "ok", message: "Сохранено" });
    } catch (err) {
      toast.showError(err);
    } finally {
      setSaving(false);
      setTimeout(() => setFlash(null), 2500);
    }
  };

  const reset = async () => {
    if (!mask.is_customized) return;
    setSaving(true);
    setFlash(null);
    try {
      const updated = await api.resetVisionProfile(mask.profile);
      onUpdated(updated);
      setForm(maskToForm(updated));
      setFlash({ kind: "ok", message: "Вернули дефолт" });
    } catch (err) {
      toast.showError(err);
    } finally {
      setSaving(false);
      setTimeout(() => setFlash(null), 2500);
    }
  };

  return (
    <article className="surface-card p-5">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start justify-between gap-4 text-left"
        aria-expanded={expanded}
      >
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
              {PROFILE_LABEL[mask.profile]}
            </h2>
            {mask.is_customized && (
              <span className="bg-[color:var(--accent-primary-subtle)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-[color:var(--accent-primary-hover)]">
                настроено
              </span>
            )}
          </div>
          <p className="text-[11px] uppercase tracking-wider text-[color:var(--text-muted)]">
            {PROFILE_SHORT[mask.profile]}
          </p>
          <p className="mt-1 text-sm text-[color:var(--text-secondary)]">
            {PROFILE_EXPLAIN[mask.profile]}
          </p>
          <BalanceBar
            storyWeight={form.story_weight}
            className="mt-3 w-full max-w-sm"
          />
        </div>
        <svg
          viewBox="0 0 20 20"
          aria-hidden="true"
          className={`h-5 w-5 shrink-0 text-[color:var(--text-muted)] transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
        >
          <path
            fill="currentColor"
            d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.06l3.71-3.83a.75.75 0 1 1 1.08 1.04l-4.25 4.39a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z"
          />
        </svg>
      </button>

      {expanded && (
        <div className="mt-5 flex flex-col gap-6 border-t border-[color:var(--border-subtle)] pt-5">
          <section className="flex flex-col gap-3">
            <header>
              <h3 className="text-sm font-semibold text-[color:var(--text-primary)]">
                Что искать в видео
              </h3>
              <p className="mt-0.5 text-[11px] text-[color:var(--text-muted)]">
                Шесть направлений анализа — включи те, что имеют смысл для
                этого типа съёмок.
              </p>
            </header>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {AGENT_NAMES.map((agent) => (
                <AgentToggle
                  key={agent}
                  agent={agent}
                  checked={form.enabled_agents.has(agent)}
                  onChange={(v) => updateAgents(agent, v)}
                />
              ))}
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <header>
              <h3 className="text-sm font-semibold text-[color:var(--text-primary)]">
                Как ранжировать найденное
              </h3>
              <p className="mt-0.5 text-[11px] text-[color:var(--text-muted)]">
                На что делать упор, когда выбираем лучшие куски.
              </p>
            </header>
            <SliderRow
              label="Речь и сюжет"
              rightLabel="Картинка"
              value={form.story_weight}
              min={0}
              max={1}
              step={0.05}
              format={(v) =>
                `Сюжет ${Math.round(v * 100)}% · Картинка ${Math.round((1 - v) * 100)}%`
              }
              onChange={(v) =>
                setForm((prev) => ({ ...prev, story_weight: v }))
              }
            />
          </section>

          <section className="flex flex-col gap-4">
            <header>
              <h3 className="text-sm font-semibold text-[color:var(--text-primary)]">
                Как вести кадр за объектом
              </h3>
              <p className="mt-0.5 text-[11px] text-[color:var(--text-muted)]">
                Три регулятора плавности — влияют на зум и отслеживание лица.
              </p>
            </header>
            <SliderRow
              label="Плавность следования"
              rightLabel="Мгновенно"
              value={form.ema_alpha}
              min={0.05}
              max={1.0}
              step={0.01}
              format={(v) => `${v.toFixed(2)} (меньше — плавнее)`}
              onChange={(v) =>
                setForm((prev) => ({ ...prev, ema_alpha: v }))
              }
            />
            <SliderRow
              label="Мёртвая зона"
              rightLabel="Подвижная"
              value={form.dead_zone_norm}
              min={0.005}
              max={0.1}
              step={0.005}
              format={(v) =>
                `${(v * 100).toFixed(1)}% кадра (меньше — кадр быстрее реагирует)`
              }
              onChange={(v) =>
                setForm((prev) => ({ ...prev, dead_zone_norm: v }))
              }
            />
            <SliderRow
              label="Сдвиг по правилу третей"
              rightLabel="Ниже"
              value={form.rule_of_thirds_y_shift}
              min={0.0}
              max={0.4}
              step={0.01}
              format={(v) =>
                v === 0
                  ? "Без сдвига (лицо по центру)"
                  : `${(v * 100).toFixed(0)}% — лицо выше центра`
              }
              onChange={(v) =>
                setForm((prev) => ({ ...prev, rule_of_thirds_y_shift: v }))
              }
            />
          </section>

          <div className="flex flex-wrap items-center gap-3 border-t border-[color:var(--border-subtle)] pt-5">
            <button
              type="button"
              onClick={save}
              disabled={saving || !dirty}
              className="rounded-lg bg-[color:var(--accent-primary)] px-4 py-2 text-sm font-semibold text-[color:var(--accent-on-primary)] transition-colors hover:bg-[color:var(--accent-primary-hover)] disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)]"
            >
              {saving ? "Сохраняем…" : "Сохранить"}
            </button>
            <button
              type="button"
              onClick={reset}
              disabled={saving || !mask.is_customized}
              className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-2 text-sm text-[color:var(--text-secondary)] transition-colors hover:border-[color:var(--text-primary)] hover:text-[color:var(--text-primary)] disabled:cursor-not-allowed disabled:text-[color:var(--text-disabled)] disabled:hover:border-[color:var(--border-default)]"
            >
              Вернуть как было
            </button>
            {flash && (
              <span
                className={`text-xs font-medium ${
                  flash.kind === "ok"
                    ? "text-[color:var(--success)]"
                    : "text-[color:var(--danger)]"
                }`}
              >
                {flash.message}
              </span>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function AgentToggle({
  agent,
  checked,
  onChange,
}: {
  agent: AgentName;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors ${
        checked
          ? "border-[color:var(--accent-primary)] bg-[color:var(--accent-primary-subtle)]"
          : "border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] hover:border-[color:var(--border-default)]"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 accent-[color:var(--accent-primary)]"
      />
      <span className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-[color:var(--text-primary)]">
          {AGENT_LABEL[agent]}
        </span>
        <span className="text-[11px] leading-snug text-[color:var(--text-muted)]">
          {AGENT_HINT[agent]}
        </span>
      </span>
    </label>
  );
}

function SliderRow({
  label,
  rightLabel,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string;
  rightLabel?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-[color:var(--text-primary)]">{label}</span>
        {rightLabel && (
          <span className="text-[11px] text-[color:var(--text-muted)]">
            {rightLabel}
          </span>
        )}
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[color:var(--accent-primary)]"
      />
      <span className="text-[11px] text-[color:var(--text-muted)]">
        {format(value)}
      </span>
    </div>
  );
}

function BalanceBar({
  storyWeight,
  className,
}: {
  storyWeight: number;
  className?: string;
}) {
  const storyPct = Math.round(storyWeight * 100);
  return (
    <div className={`flex flex-col gap-1 ${className ?? ""}`}>
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-[color:var(--text-muted)]">
        <span>Сюжет {storyPct}%</span>
        <span>{100 - storyPct}% картинка</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]">
        <div
          className="h-full rounded-full bg-[color:var(--accent-primary)] transition-[width]"
          style={{ width: `${storyPct}%` }}
        />
      </div>
    </div>
  );
}

function formsEqual(a: FormState, b: FormState): boolean {
  if (a.enabled_agents.size !== b.enabled_agents.size) return false;
  for (const agent of a.enabled_agents) {
    if (!b.enabled_agents.has(agent)) return false;
  }
  return (
    Math.abs(a.story_weight - b.story_weight) < 1e-6 &&
    Math.abs(a.dead_zone_norm - b.dead_zone_norm) < 1e-6 &&
    Math.abs(a.ema_alpha - b.ema_alpha) < 1e-6 &&
    Math.abs(a.rule_of_thirds_y_shift - b.rule_of_thirds_y_shift) < 1e-6
  );
}
