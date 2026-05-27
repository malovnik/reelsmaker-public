/**
 * Тонкий compat-слой над react-router-dom v7, повторяющий API
 * `next/navigation` ровно в том объёме, в каком фронт его реально
 * использует: `usePathname`, `useRouter` (с методами push / replace /
 * back / forward / refresh) и `useSearchParams`.
 *
 * Сохранён исходный набор сигнатур, чтобы не трогать места вызова
 * по всему дереву компонентов. Семантика — нативный react-router,
 * никакой эмуляции серверного префетча (его в нашем SPA нет и не было).
 */
import { useCallback, useMemo } from "react";
import {
  useLocation,
  useNavigate,
  useSearchParams as useSearchParamsRR,
  type NavigateOptions,
} from "react-router-dom";

export function usePathname(): string {
  return useLocation().pathname;
}

export interface AppRouter {
  push(href: string, options?: NavigateOptions): void;
  replace(href: string, options?: NavigateOptions): void;
  back(): void;
  forward(): void;
  refresh(): void;
  prefetch(_href: string): void;
}

export function useRouter(): AppRouter {
  const navigate = useNavigate();

  const push = useCallback(
    (href: string, options?: NavigateOptions) => {
      navigate(href, options);
    },
    [navigate],
  );

  const replace = useCallback(
    (href: string, options?: NavigateOptions) => {
      navigate(href, { ...options, replace: true });
    },
    [navigate],
  );

  const back = useCallback(() => {
    navigate(-1);
  }, [navigate]);

  const forward = useCallback(() => {
    navigate(1);
  }, [navigate]);

  const refresh = useCallback(() => {
    window.location.reload();
  }, []);

  const prefetch = useCallback((_href: string) => {
    // SPA: prefetch на стороне клиента не имеет смысла —
    // chunk-splitting Vite уже грузит lazy routes по требованию.
  }, []);

  return useMemo<AppRouter>(
    () => ({ push, replace, back, forward, refresh, prefetch }),
    [push, replace, back, forward, refresh, prefetch],
  );
}

export const useSearchParams = useSearchParamsRR;

/**
 * `next/navigation.notFound()` бросал спецошибку, которую ловил
 * Next-роутер и показывал not-found страницу. В react-router этого
 * нативного механизма нет: место вызова всегда внутри loader'а либо
 * data-route, поэтому корректнее всего бросать `Response 404`, который
 * react-router превратит в `errorElement`.
 */
export function notFound(): never {
  throw new Response("Not Found", { status: 404 });
}
