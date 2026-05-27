/**
 * Минимальный объединитель классов. Без зависимостей (clsx/tailwind-merge не
 * в package.json) — фильтрует falsy, склеивает через пробел.
 */
export type ClassValue = string | number | bigint | boolean | null | undefined;

export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(" ");
}
