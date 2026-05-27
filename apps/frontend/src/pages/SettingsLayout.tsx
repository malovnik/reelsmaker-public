import { Outlet } from "react-router-dom";
import { SettingsSubNav } from "@/components/settings/SettingsSubNav";

export default function SettingsLayout() {
  return (
    <main className="page-shell">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr] lg:gap-8">
        <aside className="lg:sticky lg:top-20 lg:self-start">
          <SettingsSubNav />
        </aside>
        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
    </main>
  );
}
