
import { useEffect, useRef, useState } from "react";

export type TranscriptCacheState = "hit" | "miss";

export interface JobSseEvent {
  stage?: string;
  status?: string;
  progress?: number;
  message?: string | null;
  error?: string | null;
  job_id?: string;
  reel_count?: number;
  transcript_cache?: TranscriptCacheState;
  transcript_cache_reason?: string;
  video_hash?: string;
  cached_word_count?: number;
  cached_wpm?: number;
  cached_backend?: string;
  cached_model?: string;
  cached_duration_sec?: number;
  word_count?: number;
  language?: string;
  [key: string]: unknown;
}

export interface UseJobSseResult {
  lastEvent: JobSseEvent | null;
  connected: boolean;
  finalStatus: "done" | "error" | "cancelled" | null;
  error: string | null;
  reconnectAttempt: number;
}

const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 15_000] as const;

/**
 * Base URL для прямого подключения к backend SSE.
 *
 * При установке `VITE_BACKEND_URL` (например `http://127.0.0.1:8000`)
 * EventSource подключается напрямую к backend'у в обход Vite proxy —
 * это снимает любые риски утечек на dev-прокси при длинных SSE-сессиях.
 * Если переменная не задана — используем относительный путь, и Vite
 * proxy (см. vite.config.ts) корректно пропускает SSE наружу.
 */
const SSE_BASE_URL = import.meta.env.VITE_BACKEND_URL ?? "";

export function useJobSse(jobId: string | null): UseJobSseResult {
  const [lastEvent, setLastEvent] = useState<JobSseEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const [finalStatus, setFinalStatus] = useState<
    "done" | "error" | "cancelled" | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const sourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const finalRef = useRef<"done" | "error" | "cancelled" | null>(null);

  useEffect(() => {
    if (!jobId) return;

    attemptRef.current = 0;
    finalRef.current = null;

    const connect = () => {
      const url = `${SSE_BASE_URL}/api/v1/jobs/${jobId}/stream`;
      const source = new EventSource(url);
      sourceRef.current = source;

      source.onopen = () => {
        setConnected(true);
        setError(null);
        attemptRef.current = 0;
        setReconnectAttempt(0);
      };

      source.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as JobSseEvent;
          setLastEvent(data);
          const status = data.status;
          if (
            status === "done" ||
            status === "error" ||
            status === "cancelled"
          ) {
            finalRef.current = status;
            setFinalStatus(status);
            source.close();
            setConnected(false);
          }
        } catch (parseErr) {
          setError(`cannot parse SSE event: ${String(parseErr)}`);
        }
      };

      source.onerror = () => {
        setConnected(false);
        source.close();
        if (finalRef.current !== null) {
          // Job уже финализирован — переподключаться нет смысла.
          return;
        }
        const attempt = attemptRef.current;
        if (attempt >= RECONNECT_DELAYS_MS.length) {
          setError(
            `SSE disconnected after ${RECONNECT_DELAYS_MS.length} attempts — перезагрузи страницу`,
          );
          return;
        }
        const delay = RECONNECT_DELAYS_MS[attempt];
        setError(
          `соединение прервано, переподключение через ${Math.round(
            delay / 1000,
          )}с (попытка ${attempt + 1}/${RECONNECT_DELAYS_MS.length})`,
        );
        attemptRef.current = attempt + 1;
        setReconnectAttempt(attempt + 1);
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };
  }, [jobId]);

  return { lastEvent, connected, finalStatus, error, reconnectAttempt };
}
