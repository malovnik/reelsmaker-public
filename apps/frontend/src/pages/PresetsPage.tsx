import { useLoaderData } from "react-router-dom";
import { schedulerApi } from "@/lib/api";
import { CaptionPresetsDashboard } from "@/components/scheduler/CaptionPresetsDashboard";
import type { AccountProfile, CaptionPreset } from "@/lib/api/scheduler";

interface PresetsLoaderData {
  presets: CaptionPreset[];
  profiles: AccountProfile[];
  error: string | null;
}

export async function loader(): Promise<PresetsLoaderData> {
  try {
    const [presets, profiles] = await Promise.all([
      schedulerApi.listPresets(),
      schedulerApi.listProfiles(),
    ]);
    return { presets, profiles, error: null };
  } catch (exc) {
    return {
      presets: [],
      profiles: [],
      error: exc instanceof Error ? exc.message : String(exc),
    };
  }
}

export default function PresetsPage() {
  const { presets, profiles, error } = useLoaderData() as PresetsLoaderData;
  return (
    <main className="page-shell">
      <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Caption-пресеты
        </h1>
        <p className="page-subtitle">
          Шаблоны текста, которые автоматически добавляются в начало или конец
          описания. Могут быть глобальными (для всех аккаунтов) или
          привязанными к конкретному аккаунту.
        </p>
      </header>

      <CaptionPresetsDashboard
        initialPresets={presets}
        profiles={profiles}
        initialError={error}
      />
      </div>
    </main>
  );
}
