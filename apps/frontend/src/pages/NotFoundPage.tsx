import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";

/**
 * Универсальный errorElement: показывает 404 для notFound() из loader'ов
 * и общий fallback для прочих ошибок (например fetch упал).
 */
export default function NotFoundPage() {
  const error = useRouteError();
  const isNotFound = isRouteErrorResponse(error) && error.status === 404;

  return (
    <main className="mx-auto flex min-h-[60vh] w-full max-w-3xl flex-col items-start justify-center gap-4 px-4 py-16 sm:px-6 lg:px-8">
      <div className="mono micro mute uppercase tracking-[0.18em]">
        {isNotFound ? "404" : "ошибка"}
      </div>
      <h1 className="display-serif text-4xl tracking-tight text-[color:var(--text-primary)]">
        {isNotFound
          ? "Такой страницы у Reelibra нет"
          : "Сломалось"}
      </h1>
      <p className="max-w-xl text-sm text-[color:var(--text-secondary)]">
        {isNotFound
          ? "Может, ссылка устарела или нарезку удалили. Вернись в Студию — там всё что осталось."
          : describeError(error)}
      </p>
      <Link
        to="/"
        className="mt-4 inline-flex items-center gap-2 rounded-md border border-[color:var(--border-default)] px-4 py-2 text-sm transition-colors hover:bg-[color:var(--surface-sunken)]"
      >
        ← В Студию
      </Link>
    </main>
  );
}

function describeError(error: unknown): string {
  if (isRouteErrorResponse(error)) {
    return `Сервер ответил ${error.status} ${error.statusText}. Попробуй перезагрузить страницу — если повторится, значит дело на нашей стороне.`;
  }
  if (error instanceof Error) {
    return `${error.message}. Перезагрузи страницу — если та же ошибка, проверь что Reelibra запущена (./run.sh).`;
  }
  return "Перезагрузи страницу. Если повторится — проверь что Reelibra запущена через ./run.sh.";
}
