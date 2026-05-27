/**
 * Shared HTTP infrastructure for the API client.
 *
 * Every domain module in `@/lib/api/*` imports `request` / `resolveUrl` /
 * `ApiError` from this file. Do not add domain-specific logic here.
 */

export interface HealthResponse {
  status: "ok";
  llm_providers: string[];
  transcribers: string[];
  defaults: Record<string, string>;
  chunking: {
    threshold: number;
    window: number;
    overlap: number;
    max_concurrency: number;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Resolve a relative API path against the configured backend URL.
 *
 * SPA на Vite: путь всегда относительный — все `/api/v1/*` запросы идут
 * через dev-proxy (vite.config.ts → server.proxy) или через тот же origin
 * в production. Полные URL пропускаются как есть.
 */
export function resolveUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return path;
}

export async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(resolveUrl(path), {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const coreApi = {
  health: () => request<HealthResponse>("/api/v1/health"),
};
