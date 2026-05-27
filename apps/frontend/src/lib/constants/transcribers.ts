/**
 * Транскрайберы (движки распознавания речи) — общий источник лейблов и текстов.
 *
 * Список доступных движков платформо-зависим и приходит ТОЛЬКО с бэкенда
 * (`/api/v1/health.transcribers` = `available_transcribers`). На macOS это
 * локальные MLX-движки (+ Deepgram при наличии ключа), на Windows/Linux —
 * только Deepgram при наличии ключа, иначе пусто. Фронт НЕ хардкодит список:
 * показывает ровно то, что вернул бэкенд.
 */

/** Человеческие лейблы движков. Ключи — идентификаторы из бэкенда. */
export const TRANSCRIBER_LABEL: Record<string, string> = {
  stable_ts_mlx: "Локально (Apple Silicon, точные тайминги)",
  mlx_whisper: "Локально MLX",
  deepgram: "Deepgram (облако)",
};

export function transcriberLabel(id: string): string {
  return TRANSCRIBER_LABEL[id] ?? id;
}

/**
 * Сообщение для пустого списка (Windows/Linux без ключа Deepgram). Бэкенд не
 * нашёл ни одного движка — выбирать нечего, объясняем почему и что делать.
 */
export const NO_TRANSCRIBER_MESSAGE =
  "Для распознавания речи на Windows/Linux нужен ключ Deepgram (настройки → .env). На macOS работает локально без ключа.";
