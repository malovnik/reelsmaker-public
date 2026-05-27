import { cn } from "./cn";

export interface SkeletonProps {
  className?: string;
  /** Семантический ARIA-лейбл загрузки (по умолчанию скрыт от AT). */
  label?: string;
}

/**
 * Скелетон-блок: --ink-2 подложка + одно-направленный shimmer (--ink-4),
 * прямые углы. prefers-reduced-motion → статичная подложка без прохода.
 * Габариты задаются className под форму будущего контента.
 */
export function Skeleton({ className, label }: SkeletonProps) {
  return (
    <span
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(
        "block overflow-hidden rounded-none bg-[var(--ink-2)]",
        "relative isolate",
        "motion-safe:before:absolute motion-safe:before:inset-0 motion-safe:before:-translate-x-full",
        "motion-safe:before:bg-gradient-to-r motion-safe:before:from-transparent motion-safe:before:via-[var(--ink-4)] motion-safe:before:to-transparent",
        "motion-safe:before:animate-[skeleton-shimmer_1.2s_linear_infinite] motion-safe:before:content-['']",
        className,
      )}
    />
  );
}

export interface SkeletonGridProps {
  /** Сколько карточек-плейсхолдеров. */
  count?: number;
  className?: string;
}

/** Сетка скелетон-карточек 9:16 для галереи рилсов. */
export function SkeletonReelGrid({ count = 6, className }: SkeletonGridProps) {
  return (
    <div
      role="status"
      aria-label="Загрузка рилсов"
      className={cn(
        "grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5",
        className,
      )}
    >
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="aspect-[9/16] w-full" />
      ))}
    </div>
  );
}

/** Скелетон строки списка (заголовок + мета). */
export function SkeletonRow({ className }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Загрузка"
      className={cn("flex flex-col gap-2 border-b border-[var(--line-soft)] py-3", className)}
    >
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-3 w-1/3" />
    </div>
  );
}
