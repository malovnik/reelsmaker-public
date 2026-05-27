import { useLoaderData } from "react-router-dom";
import { api, type ProfileMaskRead } from "@/lib/api";
import { VisionProfilesSettingsClient } from "@/components/VisionProfilesSettingsClient";

export async function loader(): Promise<ProfileMaskRead[]> {
  try {
    return await api.listVisionProfiles();
  } catch {
    return [];
  }
}

export default function VisionProfilesPage() {
  const profiles = useLoaderData() as ProfileMaskRead[];
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Профили нарезки
        </h1>
        <p className="page-subtitle">
          Профиль задаёт, на чём система делает упор при поиске моментов:
          речь, эмоции, визуал. Все параметры можно перенастроить под свой
          контент. Кнопка «Вернуть как было» возвращает параметры к
          оригинальным значениям.
        </p>
      </header>
      <VisionProfilesSettingsClient initial={profiles} />
    </div>
  );
}
