import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { NavRail } from "./NavRail";
import { TopBar } from "./TopBar";
import { Onboarding } from "./Onboarding";

interface Props {
  children: ReactNode;
}

export function AppShell({ children }: Props) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const location = useLocation();

  // Закрываем drawer при переходе на другой маршрут — иначе на mobile
  // навигация открывает страницу, но drawer остаётся поверх контента.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  // Esc закрывает drawer когда он открыт.
  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileNavOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileNavOpen]);

  const openNav = useCallback(() => setMobileNavOpen(true), []);
  const closeNav = useCallback(() => setMobileNavOpen(false), []);

  return (
    <div className="flex min-h-screen w-full">
      {/* Cinematic grain overlay — оживляет тёплый dark, едва заметно */}
      <div className="grain" aria-hidden="true" />
      <NavRail mobileOpen={mobileNavOpen} onClose={closeNav} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenNav={openNav} />
        <div className="flex-1">{children}</div>
      </div>
      <Onboarding />
    </div>
  );
}
