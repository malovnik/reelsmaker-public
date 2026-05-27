
import {
  Group,
  NumberRow,
  SelectRow,
  SliderRow,
  SwitchRow,
} from "@/components/settings-shared";
import type { GroupProps } from "./types";

const PROXY_MAX_DIM_OPTIONS = [720, 1080, 1440, 1920, 2560] as const;
const PROXY_AUDIO_BITRATE_OPTIONS = [64, 96, 128, 192, 256, 320] as const;

export function ProxyGroup({ values, update }: GroupProps) {
  const proxyDisabled = !values.proxy_enabled;
  return (
    <Group title="Рабочая копия">
      <SwitchRow
        id="proxy_enabled"
        label="Создавать облегчённую копию после загрузки"
        hint="Копия в 1080p для быстрой обработки. Сохраняется в кэше и переиспользуется между нарезками."
        checked={values.proxy_enabled}
        onChange={(v) => update("proxy_enabled", v)}
      />
      <SelectRow
        id="proxy_max_dim"
        label="Максимальное разрешение копии"
        hint="Если исходник меньше — оставляем как есть, не увеличиваем."
        value={values.proxy_max_dim}
        options={PROXY_MAX_DIM_OPTIONS.map((v) => ({
          value: v,
          label: `${v} px`,
        }))}
        disabled={proxyDisabled}
        onChange={(v) => update("proxy_max_dim", v)}
      />
      <SliderRow
        id="proxy_video_crf"
        label="Качество сжатия"
        hint="18 — максимальное качество, 23 — стандартное, 30 — заметное сжатие."
        value={values.proxy_video_crf}
        min={18}
        max={30}
        step={1}
        disabled={proxyDisabled}
        onChange={(v) => update("proxy_video_crf", v)}
      />
      <NumberRow
        id="proxy_video_maxrate_kbps"
        label="Максимальная скорость видеопотока"
        hint="кбит/с. Ограничивает пиковое значение, чтобы файл не раздувался."
        unit="кбит/с"
        value={values.proxy_video_maxrate_kbps}
        min={1000}
        max={20000}
        step={500}
        disabled={proxyDisabled}
        onChange={(v) => update("proxy_video_maxrate_kbps", v)}
      />
      <SelectRow
        id="proxy_audio_bitrate_kbps"
        label="Качество звука"
        hint="128 кбит/с — хватает для речи и музыки."
        value={values.proxy_audio_bitrate_kbps}
        options={PROXY_AUDIO_BITRATE_OPTIONS.map((v) => ({
          value: v,
          label: `${v} кбит/с`,
        }))}
        disabled={proxyDisabled}
        onChange={(v) => update("proxy_audio_bitrate_kbps", v)}
      />
    </Group>
  );
}
