
import { Group, NumberRow } from "@/components/settings-shared";
import type { GroupProps } from "./types";

export function ProxyCacheGroup({ values, update }: GroupProps) {
  const proxyDisabled = !values.proxy_enabled;
  return (
    <Group title="Кэш рабочих копий">
      <NumberRow
        id="proxy_cache_max_gb"
        label="Максимальный размер кэша"
        hint="ГБ. Старые файлы удаляются автоматически, когда кэш переполнен."
        unit="ГБ"
        value={values.proxy_cache_max_gb}
        min={5}
        max={500}
        step={5}
        disabled={proxyDisabled}
        onChange={(v) => update("proxy_cache_max_gb", v)}
      />
      <NumberRow
        id="proxy_lock_timeout_sec"
        label="Время ожидания блокировки"
        hint="После этого времени зависший процесс считается мёртвым и удаляется."
        unit="сек"
        value={values.proxy_lock_timeout_sec}
        min={60}
        max={14400}
        step={60}
        disabled={proxyDisabled}
        onChange={(v) => update("proxy_lock_timeout_sec", v)}
      />
    </Group>
  );
}
