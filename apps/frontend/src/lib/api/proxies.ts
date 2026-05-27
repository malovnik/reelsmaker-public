import { request } from "./core";

/**
 * R8.1 — клиент управления кэшем proxy-файлов.
 * Бэк: routes/proxies.py (prefix /api/v1/proxies).
 *   GET    /proxies          — список proxy в кэше
 *   DELETE /proxies/cleanup  — LRU-cleanup до max_gb
 *   DELETE /proxies/{sha256} — удалить proxy конкретного source
 */

export interface ProxyEntry {
  sha256: string;
  profile_id: string;
  path: string;
  file_size_bytes: number;
  file_size_mb: number;
  mtime: number;
  age_sec: number;
}

export interface ProxyListResponse {
  items: ProxyEntry[];
  total_count: number;
  total_size_bytes: number;
  total_size_mb: number;
}

export interface ProxyCleanupResponse {
  deleted: number;
  freed_bytes: number;
  freed_mb: number;
  requested_max_gb: number;
}

export const proxiesApi = {
  listProxies: () => request<ProxyListResponse>("/api/v1/proxies"),
  cleanupProxies: (maxGb?: number) =>
    request<ProxyCleanupResponse>(
      `/api/v1/proxies/cleanup${maxGb !== undefined ? `?max_gb=${maxGb}` : ""}`,
      { method: "DELETE" },
    ),
  deleteProxy: (sha256: string) =>
    request<void>(`/api/v1/proxies/${encodeURIComponent(sha256)}`, {
      method: "DELETE",
    }),
};
