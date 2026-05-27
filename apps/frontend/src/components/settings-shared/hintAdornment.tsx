import { Tooltip, Badge, HONESTY_LABELS } from "@/components/ui";
import { getControlHint, type ControlHintKey } from "./controlHints";

/**
 * Общая логика подсказки для всех settings-примитивов (Эксперт-студия §2).
 *
 * Если передан `hintKey` — подсказка берётся из реестра `controlHints`:
 *  • инлайн-строка под контролом = `what` (всегда видима),
 *  • (i)-иконка рядом с меткой раскрывает full-tooltip (what/effect/advise+бейдж),
 *  • honesty-бейдж рендерится у метки.
 * Иначе — fallback на переданную строку `hint` (обратная совместимость).
 */
export interface HintSource {
  /** Ключ реестра подсказок. Тип гарантирует существование записи. */
  hintKey?: ControlHintKey;
  /** Legacy/fallback-строка, если ключ не задан. */
  hint?: string;
}

export interface ResolvedHint {
  /** Текст инлайн-подсказки под контролом. */
  inline: string;
  /** Иконка-триггер full-tooltip рядом с меткой (или null). */
  adornment: React.ReactNode;
  /** Honesty-бейдж рядом с меткой (или null). */
  badgeNode: React.ReactNode;
}

export function resolveHint({ hintKey, hint }: HintSource): ResolvedHint {
  if (hintKey) {
    const h = getControlHint(hintKey);
    return {
      inline: h.what,
      adornment: (
        <Tooltip what={h.what} effect={h.effect} advise={h.advise} badge={h.badge} side="left" />
      ),
      badgeNode: h.badge ? (
        <Badge variant={h.badge} pixel>
          {HONESTY_LABELS[h.badge]}
        </Badge>
      ) : null,
    };
  }
  return { inline: hint ?? "", adornment: null, badgeNode: null };
}
