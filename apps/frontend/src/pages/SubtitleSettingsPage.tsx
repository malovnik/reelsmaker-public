import { useLoaderData } from "react-router-dom";
import {
  api,
  type FontListResponse,
  type SubtitleStylePreset,
} from "@/lib/api";
import { SubtitleSettingsClient } from "@/components/SubtitleSettingsClient";

interface SubtitleLoaderData {
  presets: SubtitleStylePreset[];
  fonts: FontListResponse;
}

export async function loader(): Promise<SubtitleLoaderData> {
  const fallbackFonts: FontListResponse = {
    fonts: [],
    scanned_at: null,
    source: "fallback",
  };
  try {
    const [presets, fontList] = await Promise.all([
      api.listSubtitlePresets(),
      api.listFonts(),
    ]);
    return { presets, fonts: fontList };
  } catch {
    return { presets: [], fonts: fallbackFonts };
  }
}

export default function SubtitleSettingsPage() {
  const { presets, fonts } = useLoaderData() as SubtitleLoaderData;
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Стили субтитров
        </h1>
        <p className="page-subtitle">
          Пресеты применятся к следующим нарезкам. Превью показывает, как
          субтитры лягут в финальный рилс — позиция, отступы, обводка и
          подложка считаются так же, как в рендере.
        </p>
      </header>

      {presets.length === 0 ? (
        <div className="rounded-lg border border-dashed border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-6 text-sm text-[color:var(--danger)]">
          Пресетов нет — сервер не отвечает или ещё не успел отдать список.
          Запусти{" "}
          <code className="rounded bg-[color:var(--surface-sunken)] px-1 py-0.5 font-mono text-[12px]">
            ./run.sh
          </code>{" "}
          и обнови страницу.
        </div>
      ) : (
        <SubtitleSettingsClient
          initialPresets={presets}
          initialFonts={fonts}
        />
      )}
    </div>
  );
}
