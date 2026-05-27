
import { Link } from "react-router-dom";
import {
  AGENT_NAMES,
  VISION_PROFILES,
  type AgentName,
  type ProfileMaskRead,
  type VisionProfile,
} from "@/lib/api";

interface ProfileMeta {
  id: VisionProfile;
  title: string;
  subtitle: string;
  description: string;
  color: string;
}

const PROFILES: ProfileMeta[] = [
  {
    id: "talking_head",
    title: "Говорящая голова",
    subtitle: "подкасты, интервью, выступления",
    description:
      "Для форматов, где главное — речь. Следим за композицией лица в кадре.",
    color: "var(--profile-talking-head)",
  },
  {
    id: "fashion",
    title: "Фэшн и стиль",
    subtitle: "показы, lookbook, beauty",
    description:
      "Для модных съёмок. Склеиваем сцены одного человека между локациями.",
    color: "var(--profile-fashion)",
  },
  {
    id: "travel",
    title: "Путешествия",
    subtitle: "приключения, природа, город",
    description:
      "Для видео без диалогов. Выбираем самые выразительные моменты по картинке.",
    color: "var(--profile-travel)",
  },
  {
    id: "screencast",
    title: "Скринкаст",
    subtitle: "туториалы, демо интерфейса",
    description:
      "Для записи экрана. Следим за курсором, увеличиваем активную область.",
    color: "var(--profile-screencast)",
  },
  {
    id: "custom",
    title: "Своя настройка",
    subtitle: "нестандартные сценарии",
    description:
      "Настраивай сам: какие смыслы ищем и насколько плавно ведём кадр.",
    color: "var(--profile-custom)",
  },
];

const AGENT_LABEL: Record<AgentName, string> = {
  hook_hunter: "Крючки в начале",
  emotional_peak_finder: "Эмоциональные пики",
  humor_specialist: "Шутки и смех",
  dramatic_irony_scanner: "Ирония и противоречия",
  thesis_extractor: "Главные тезисы",
  motif_tracker: "Повторяющиеся мотивы",
};

interface Props {
  value: VisionProfile;
  onChange: (profile: VisionProfile) => void;
  masks?: ProfileMaskRead[];
}

export function ProfileSelector({ value, onChange, masks = [] }: Props) {
  const masksByProfile = new Map<VisionProfile, ProfileMaskRead>(
    masks.map((m) => [m.profile, m]),
  );
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {PROFILES.map((p) => {
        const selected = p.id === value;
        const mask = masksByProfile.get(p.id);
        return (
          <div key={p.id} className="group relative">
            <button
              type="button"
              onClick={() => onChange(p.id)}
              aria-pressed={selected}
              className={[
                "relative flex w-full flex-col items-start gap-1.5 overflow-hidden rounded-xl border p-4 text-left outline-none transition-all duration-200",
                selected
                  ? "bg-[color:var(--surface-raised)] shadow-[var(--shadow-md)]"
                  : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] hover:-translate-y-0.5 hover:shadow-[var(--shadow-sm)]",
              ].join(" ")}
              style={
                selected
                  ? {
                      borderColor: p.color,
                      boxShadow: `0 0 0 1px ${p.color}, var(--shadow-md)`,
                    }
                  : undefined
              }
            >
              <span
                aria-hidden="true"
                className={`absolute inset-x-0 top-0 h-0.5 transition-opacity duration-200 ${
                  selected ? "opacity-100" : "opacity-0 group-hover:opacity-60"
                }`}
                style={{ backgroundColor: p.color }}
              />

              <div className="relative flex w-full items-start justify-between gap-3">
                <span className="text-sm font-semibold tracking-tight text-[color:var(--text-primary)]">
                  {p.title}
                </span>
                <div className="flex shrink-0 items-center gap-1.5">
                  {mask?.is_customized && (
                    <span
                      className="rounded-full bg-[color:var(--accent-primary-subtle)] px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider text-[color:var(--accent-primary-hover)]"
                      title="Этот профиль ты уже настраивал"
                    >
                      настроено
                    </span>
                  )}
                  {selected && (
                    <span
                      className="flex size-5 items-center justify-center rounded-full text-[10px] text-white shadow-sm"
                      style={{ backgroundColor: p.color }}
                      aria-hidden="true"
                    >
                      ✓
                    </span>
                  )}
                </div>
              </div>

              <span className="relative text-[11px] uppercase tracking-wider text-[color:var(--text-muted)]">
                {p.subtitle}
              </span>

              <p className="relative mt-1 text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
                {p.description}
              </p>
            </button>
            {mask && <ProfileTooltip mask={mask} accent={p.color} />}
          </div>
        );
      })}
    </div>
  );
}

function ProfileTooltip({
  mask,
  accent,
}: {
  mask: ProfileMaskRead;
  accent: string;
}) {
  const storyPct = Math.round(mask.story_weight * 100);
  const enabledCount = mask.enabled_agents.length;
  const disabled = AGENT_NAMES.filter((a) => !mask.enabled_agents.includes(a));
  return (
    <div
      role="tooltip"
      className="pointer-events-none invisible absolute left-1/2 top-full z-20 mt-2 w-72 -translate-x-1/2 translate-y-1 rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-3 opacity-0 shadow-[var(--shadow-lg)] transition-all duration-150 group-hover:visible group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:visible group-focus-within:translate-y-0 group-focus-within:opacity-100"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-muted)]">
          Что применяется
        </span>
        <Link
          to="/settings/profiles"
          className="text-[11px] text-[color:var(--text-secondary)] underline decoration-[color:var(--border-default)] underline-offset-2 transition-colors hover:text-[color:var(--text-primary)]"
        >
          Настроить
        </Link>
      </div>
      <div className="mb-2 flex items-center justify-between text-[11px] text-[color:var(--text-muted)]">
        <span>Сюжет {storyPct}%</span>
        <span>{100 - storyPct}% картинка</span>
      </div>
      <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]">
        <div
          className="h-full rounded-full transition-[width]"
          style={{ width: `${storyPct}%`, backgroundColor: accent }}
        />
      </div>
      <div className="mb-1 text-[11px] font-medium text-[color:var(--text-primary)]">
        Что ищем ({enabledCount} из {AGENT_NAMES.length})
      </div>
      <ul className="mb-2 flex flex-wrap gap-1">
        {mask.enabled_agents.map((a) => (
          <li
            key={a}
            className="rounded-md bg-[color:var(--accent-primary-subtle)] px-1.5 py-0.5 text-[10px] text-[color:var(--accent-primary-hover)]"
          >
            {AGENT_LABEL[a]}
          </li>
        ))}
      </ul>
      {disabled.length > 0 && (
        <>
          <div className="mb-1 text-[11px] font-medium text-[color:var(--text-muted)]">
            Пропускаем
          </div>
          <ul className="flex flex-wrap gap-1">
            {disabled.map((a) => (
              <li
                key={a}
                className="rounded-md bg-[color:var(--surface-sunken)] px-1.5 py-0.5 text-[10px] text-[color:var(--text-muted)] line-through decoration-dotted"
              >
                {AGENT_LABEL[a]}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export const PROFILE_LABELS: Record<VisionProfile, string> = PROFILES.reduce(
  (acc, p) => {
    acc[p.id] = p.title;
    return acc;
  },
  {} as Record<VisionProfile, string>,
);

export { VISION_PROFILES };
