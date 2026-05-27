import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import "@/lib/fonts";
import "./globals.css";

import { ErrorBoundary } from "@/components/ui";
import { UiModeProvider, ToastProvider, ConfirmProvider } from "@/contexts";
import { router } from "./router";

const container = document.getElementById("root");
if (!container) {
  throw new Error("missing #root");
}

/**
 * Дерево провайдеров (порядок снаружи внутрь):
 *   ErrorBoundary (root) — последний рубеж: ловит throw из самих провайдеров и
 *     роутера, чтобы даже сбой инициализации не дал белый экран.
 *   UiModeProvider — режим guided/expert (localStorage, no-flash); ниже него
 *     всё дерево знает режим.
 *   ToastProvider — тосты; виден из любого экрана и из ConfirmProvider.
 *   ConfirmProvider — промис-диалоги подтверждения (может слать тосты).
 *   RouterProvider — приложение.
 *
 * WizardStateProvider (R2) НЕ здесь: ему нужны route-loaded данные (models,
 * subtitlePresets, postProductionPresets, defaultUseSourceForRender), которых на
 * уровне приложения нет. Он оборачивает только мод-поддеревья Студии (guided ↔
 * expert) внутри экрана-Студии, где доступна загрузка HomePage-loader'а — это и
 * есть «над обоими режимами» из R2. Размещение — за агентом экрана Студии.
 */
createRoot(container).render(
  <StrictMode>
    <ErrorBoundary>
      <UiModeProvider>
        <ToastProvider>
          <ConfirmProvider>
            <RouterProvider router={router} />
          </ConfirmProvider>
        </ToastProvider>
      </UiModeProvider>
    </ErrorBoundary>
  </StrictMode>,
);
