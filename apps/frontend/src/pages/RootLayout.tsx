import { Outlet } from "react-router-dom";
import { AppShell } from "@/components/shell/AppShell";
import { ErrorBoundary } from "@/components/ui";

/**
 * Корневая оболочка. Outlet обёрнут в ErrorBoundary внутри AppShell —
 * рантайм-throw любого экрана ловится, рейл/шапка остаются на месте
 * (двухуровневая защита: этот boundary + route-level errorElement в router.tsx).
 */
export default function RootLayout() {
  return (
    <AppShell>
      <ErrorBoundary>
        <Outlet />
      </ErrorBoundary>
    </AppShell>
  );
}
