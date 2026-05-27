import { cn } from "@/components/ui";
import type { StatusMeta } from "./statusMeta";

interface Props {
  meta: StatusMeta;
  /** Дополнительный счётчик справа (для сводных бейджей). */
  count?: number;
  className?: string;
}

/**
 * Mono-чип статуса: символ-маркер + лейбл, цветной бордер по токену.
 * Прямые углы, прозрачный фон — в стиле Sumi-карточек.
 */
export function StatusPill({ meta, count, className }: Props) {
  return (
    <span
      className={cn(
        "mono inline-flex items-center gap-1.5 rounded-none border bg-transparent px-2 py-1 text-[0.6875rem] uppercase leading-none tracking-[0.1em]",
        className,
      )}
      style={{ color: meta.color, borderColor: meta.color }}
    >
      <span aria-hidden="true">{meta.symbol}</span>
      <span>{meta.label}</span>
      {count !== undefined ? <span className="opacity-70">· {count}</span> : null}
    </span>
  );
}
