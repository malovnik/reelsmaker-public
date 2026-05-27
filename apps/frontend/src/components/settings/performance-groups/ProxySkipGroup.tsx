
import { Group, NumberRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function ProxySkipGroup({ values, update }: GroupProps) {
  const proxyDisabled = !values.proxy_enabled;
  return (
    <Group title="Когда копия не нужна">
      <NumberRow
        id="proxy_skip_height_le"
        label="Исходник высотой меньше или равно"
        hint="пикс. Если видео уже в 1080p или меньше, копия часто не ускоряет обработку."
        unit="пикс"
        value={values.proxy_skip_height_le}
        min={240}
        max={4320}
        step={120}
        disabled={proxyDisabled}
        onChange={(v) => update("proxy_skip_height_le", v)}
      />
      <NumberRow
        id="proxy_skip_duration_lt_sec"
        label="Длительность короче"
        hint="сек. Короткое видео обрабатывается быстро и без копии."
        unit="сек"
        value={values.proxy_skip_duration_lt_sec}
        min={10}
        max={3600}
        step={30}
        disabled={proxyDisabled}
        onChange={(v) => update("proxy_skip_duration_lt_sec", v)}
      />
      <NumberRow
        id="proxy_skip_bitrate_lt_kbps"
        label="Исходник со скоростью потока ниже"
        hint="кбит/с. Лёгкое видео не выигрывает от копии."
        unit="кбит/с"
        value={values.proxy_skip_bitrate_lt_kbps}
        min={500}
        max={200000}
        step={500}
        disabled={proxyDisabled}
        onChange={(v) => update("proxy_skip_bitrate_lt_kbps", v)}
      />
    </Group>
  );
}
