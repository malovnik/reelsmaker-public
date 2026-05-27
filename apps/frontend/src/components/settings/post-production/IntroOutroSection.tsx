
import type { VideoAsset } from "@/lib/api";
import { AssetSelect, Field, Section } from "./shared";

interface Props {
  assets: VideoAsset[];
  introAssetId: number | null;
  outroAssetId: number | null;
  onIntroChange: (id: number | null) => void;
  onOutroChange: (id: number | null) => void;
}

export function IntroOutroSection({
  assets,
  introAssetId,
  outroAssetId,
  onIntroChange,
  onOutroChange,
}: Props) {
  return (
    <Section title="Интро и аутро">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="Ролик в начале">
          <AssetSelect
            assets={assets}
            value={introAssetId}
            onChange={onIntroChange}
          />
        </Field>
        <Field label="Ролик в конце">
          <AssetSelect
            assets={assets}
            value={outroAssetId}
            onChange={onOutroChange}
          />
        </Field>
      </div>
      <p className="mt-1 text-[11px] text-[color:var(--mute)]">
        Эти ролики добавляются в начало и конец каждого рилса после
        сборки. Файлы уже должны быть в нужном размере (1080×1920 для
        вертикального формата) — программа не меняет их разрешение.
      </p>
    </Section>
  );
}
