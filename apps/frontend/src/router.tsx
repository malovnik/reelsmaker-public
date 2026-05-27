import { createBrowserRouter, isRouteErrorResponse, useRouteError } from "react-router-dom";

import { Button } from "@/components/ui";

/**
 * Route-level error element. Ловит rejection lazy-чанка и брошенные loader'ом
 * ответы. Экран «Клинок затупился» в стиле брендбука (зеркалит ui/ErrorBoundary,
 * но через useRouteError — рантайм-throw компонентов ловит классовый
 * ErrorBoundary вокруг Outlet, а ошибки роутинга/чанков — этот элемент).
 *
 * Сбой загрузки чанка (новый деплой, обрыв сети) → hard reload подтянет свежий
 * манифест ассетов; обычная ошибка → возврат на главную.
 */
function RouteError() {
  const error = useRouteError();
  const isDev = import.meta.env?.DEV ?? false;

  const isChunkError =
    error instanceof Error &&
    /loading (dynamically imported module|chunk|css chunk)|importing a module script failed/i.test(
      error.message,
    );

  const detail = isChunkError
    ? "Не удалось загрузить часть приложения. Обычно помогает перезагрузка — возможно, вышло обновление."
    : "Экран не смог открыться. Это не вы — что-то в приложении. Данные целы.";

  const techDetails = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? (error.stack ?? error.message)
      : String(error);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 py-16 text-center">
      <div
        aria-hidden="true"
        className="font-[family-name:var(--font-display)] text-6xl leading-none text-[var(--copper,var(--ember))] opacity-70"
      >
        侍
      </div>

      <h1 className="mt-6 font-[family-name:var(--font-display)] text-2xl font-semibold text-[var(--paper)]">
        Клинок затупился
      </h1>

      <div className="mx-auto mt-3 h-px w-24 bg-[var(--danger)]" aria-hidden="true" />

      <p className="mt-4 max-w-md text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">
        {detail}
      </p>

      <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
        <Button variant="primary" onClick={() => window.location.reload()}>
          Перезагрузить
        </Button>
        <Button variant="ghost" onClick={() => (window.location.href = "/")}>
          На главную
        </Button>
      </div>

      {isDev && (
        <details className="mt-8 w-full max-w-lg text-left">
          <summary className="cursor-pointer font-[family-name:var(--font-mono)] text-[0.75rem] uppercase tracking-[0.1em] text-[var(--mute)]">
            Технические детали (только dev)
          </summary>
          <pre className="mt-2 overflow-auto rounded-none border border-[var(--line-soft)] bg-[var(--ink)] p-3 text-[0.75rem] leading-snug text-[var(--mute-2)]">
            {techDetails}
          </pre>
        </details>
      )}
    </div>
  );
}

/**
 * Роутинг с code-split всех экранов (R3 + bundle 705KB → split).
 *
 * Каждый роут использует свойство `lazy` React Router 7: оно разбивает на
 * отдельный чанк И компонент, И его loader (loader'ы должны быть доступны до
 * рендера, поэтому обычный React.lazy для них не годится — нужен route-level
 * lazy, отдающий { Component, loader }). React Router сам управляет состоянием
 * загрузки чанка (без мигания), а rejection чанка ловит `errorElement`.
 *
 * `errorElement: <RouteError/>` стоит на КАЖДОМ роуте (не только root) — при
 * lazy-роутах root-errorElement поглотил бы и 404, и сбой загрузки чанка в один
 * экран. Отдельные route-level errorElement дают «Перезагрузить» на сбое чанка,
 * а несуществующий путь по-прежнему ведёт в 404 (catch-all ниже).
 */

const routeError = { errorElement: <RouteError /> };

export const router = createBrowserRouter([
  {
    lazy: () => import("@/pages/RootLayout").then((m) => ({ Component: m.default })),
    errorElement: <RouteError />,
    children: [
      {
        index: true,
        ...routeError,
        lazy: () =>
          import("@/pages/HomePage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },

      {
        path: "projects",
        ...routeError,
        lazy: () =>
          import("@/pages/ProjectsPage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },
      {
        path: "projects/:id/folder",
        ...routeError,
        lazy: () =>
          import("@/pages/ProjectFolderPage").then((m) => ({
            Component: m.default,
          })),
      },

      {
        path: "jobs/:id",
        ...routeError,
        lazy: () =>
          import("@/pages/JobDetailPage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },
      {
        path: "jobs/:id/reels/:reelId",
        ...routeError,
        lazy: () =>
          import("@/pages/ClipDetailPage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },
      {
        path: "jobs/:id/tinder",
        ...routeError,
        lazy: () =>
          import("@/pages/JobTinderPage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },

      {
        path: "scheduler",
        ...routeError,
        lazy: () =>
          import("@/pages/SchedulerPage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },
      {
        path: "scheduler/accounts",
        ...routeError,
        lazy: () =>
          import("@/pages/AccountsPage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },
      {
        path: "scheduler/new",
        ...routeError,
        lazy: () =>
          import("@/pages/NewCampaignPage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },
      {
        path: "scheduler/presets",
        ...routeError,
        lazy: () =>
          import("@/pages/PresetsPage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },
      {
        path: "scheduler/campaigns/:id",
        ...routeError,
        lazy: () =>
          import("@/pages/CampaignDetailPage").then((m) => ({
            Component: m.default,
            loader: m.loader,
          })),
      },

      {
        path: "settings",
        ...routeError,
        lazy: () =>
          import("@/pages/SettingsLayout").then((m) => ({
            Component: m.default,
          })),
        children: [
          {
            path: "brand",
            ...routeError,
            lazy: () =>
              import("@/pages/BrandKitPage").then((m) => ({
                Component: m.default,
              })),
          },
          {
            path: "maintenance",
            ...routeError,
            lazy: () =>
              import("@/pages/MaintenancePage").then((m) => ({
                Component: m.default,
              })),
          },
          {
            path: "models",
            ...routeError,
            lazy: () =>
              import("@/pages/ModelsPage").then((m) => ({
                Component: m.default,
                loader: m.loader,
              })),
          },
          {
            path: "api-keys",
            ...routeError,
            lazy: () =>
              import("@/pages/ApiKeysPage").then((m) => ({
                Component: m.default,
              })),
          },
          {
            path: "performance",
            ...routeError,
            lazy: () =>
              import("@/pages/PerformanceSettingsPage").then((m) => ({
                Component: m.default,
                loader: m.loader,
              })),
          },
          {
            path: "post-production",
            ...routeError,
            lazy: () =>
              import("@/pages/PostProductionSettingsPage").then((m) => ({
                Component: m.default,
                loader: m.loader,
              })),
          },
          {
            path: "profiles",
            ...routeError,
            lazy: () =>
              import("@/pages/VisionProfilesPage").then((m) => ({
                Component: m.default,
                loader: m.loader,
              })),
          },
          {
            path: "prompts",
            ...routeError,
            lazy: () =>
              import("@/pages/PromptsPage").then((m) => ({
                Component: m.default,
                loader: m.loader,
              })),
          },
          {
            path: "subtitles",
            ...routeError,
            lazy: () =>
              import("@/pages/SubtitleSettingsPage").then((m) => ({
                Component: m.default,
                loader: m.loader,
              })),
          },
        ],
      },

      {
        path: "*",
        lazy: () =>
          import("@/pages/NotFoundPage").then((m) => ({ Component: m.default })),
      },
    ],
  },
]);
