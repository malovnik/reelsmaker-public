import { Outlet } from "react-router-dom";
import { AppShell } from "@/components/shell/AppShell";

export default function RootLayout() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
