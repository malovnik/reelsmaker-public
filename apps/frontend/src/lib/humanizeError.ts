/**
 * humanizeError — маппинг ошибок API/сети в человеческий русский текст.
 *
 * Закрывает FA3-02: вместо сырых `Ошибка 500: {"detail"...}` и
 * `JSON.stringify(err.detail)` пользователь видит понятное сообщение.
 * Сырые технические детали попадают только в `hint` и только в dev-режиме —
 * в production в UI их нет никогда.
 *
 * Чистая функция, без side-effects. Используется тостами, error boundary
 * и инлайн-ошибками форм.
 */
import { ApiError } from "@/lib/api";

export interface HumanError {
  title: string;
  detail: string;
  /** Технические подробности — показывать только в dev. */
  hint?: string;
}

/** Признак сетевой ошибки (бэкенд недоступен, CORS, оборванное соединение). */
function isNetworkError(error: unknown): boolean {
  if (error instanceof TypeError) {
    const msg = error.message.toLowerCase();
    return (
      msg.includes("failed to fetch") ||
      msg.includes("networkerror") ||
      msg.includes("network request failed") ||
      msg.includes("load failed")
    );
  }
  return false;
}

/**
 * Извлекает читаемую строку из `ApiError.detail`.
 * FastAPI 422 → `{ detail: [{ loc, msg, ... }] }`; 4xx/5xx → `{ detail: "..." }`
 * либо строка. Технические объекты не разворачиваем в UI — только короткая
 * человеческая выжимка (имя поля / текст), остальное уходит в hint.
 */
function readDetailMessage(detail: unknown): { field?: string; message?: string } {
  if (typeof detail === "string") {
    return { message: detail.trim() || undefined };
  }
  if (detail && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    const inner = obj.detail;
    // FastAPI validation: detail = массив ошибок валидации.
    if (Array.isArray(inner) && inner.length > 0) {
      const first = inner[0] as Record<string, unknown>;
      const loc = Array.isArray(first.loc) ? first.loc : [];
      const field = loc
        .filter((p): p is string => typeof p === "string" && p !== "body" && p !== "query")
        .pop();
      const msg = typeof first.msg === "string" ? first.msg : undefined;
      return { field, message: msg };
    }
    if (typeof inner === "string") {
      return { message: inner.trim() || undefined };
    }
  }
  return {};
}

/** Сырое техническое описание для dev-hint. */
function rawHint(error: unknown): string | undefined {
  if (error instanceof ApiError) {
    const raw =
      typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail);
    return `${error.status} — ${raw}`;
  }
  if (error instanceof Error) return error.message;
  if (error == null) return undefined;
  return String(error);
}

export function humanizeError(error: unknown): HumanError {
  const isDev = import.meta.env.DEV;
  const hint = isDev ? rawHint(error) : undefined;

  if (isNetworkError(error)) {
    return {
      title: "Нет связи с сервером",
      detail: "Проверьте, запущен ли бэкенд, и попробуйте ещё раз.",
      hint,
    };
  }

  if (error instanceof ApiError) {
    const { field, message } = readDetailMessage(error.detail);
    const status = error.status;

    if (status === 400 || status === 422) {
      return {
        title: "Что-то с данными формы",
        detail: field
          ? `Проверьте поле «${field}» и попробуйте снова.`
          : message ?? "Проверьте заполненные поля и попробуйте снова.",
        hint,
      };
    }
    if (status === 401 || status === 403) {
      return {
        title: "Нет доступа",
        detail: "Проверьте ключ в Настройках и попробуйте снова.",
        hint,
      };
    }
    if (status === 404) {
      return {
        title: "Не нашли",
        detail: "Возможно, запись удалили или ссылка устарела.",
        hint,
      };
    }
    if (status === 409) {
      return {
        title: "Конфликт",
        detail: "Запись уже изменилась — обновите страницу и повторите.",
        hint,
      };
    }
    if (status === 429) {
      return {
        title: "Слишком часто",
        detail: "Подождите немного и попробуйте снова.",
        hint,
      };
    }
    if (status >= 500) {
      return {
        title: "Сбой на стороне приложения",
        detail: "Данные целы. Попробуйте ещё раз через минуту.",
        hint,
      };
    }
    // Прочие 4xx — общий дружелюбный текст.
    return {
      title: "Не получилось выполнить запрос",
      detail: message ?? "Попробуйте ещё раз.",
      hint,
    };
  }

  return {
    title: "Что-то пошло не так",
    detail: "Попробуйте повторить действие.",
    hint,
  };
}
