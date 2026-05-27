import { useEffect, useState } from "react";
import { coreApi } from "@/lib/api/core";

/**
 * Индикатор связи с бэкендом (d4 §1.3). Gold-точка «онлайн» / --danger «нет
 * связи» по результату GET /api/v1/health. Пингует при монтировании и каждые
 * 60с. Подпись скрыта на узких экранах, точка видна всегда.
 */

type State = "checking" | "online" | "offline";

export function HealthIndicator() {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    let alive = true;

    const ping = async () => {
      try {
        await coreApi.health();
        if (alive) setState("online");
      } catch {
        if (alive) setState("offline");
      }
    };

    void ping();
    const timer = window.setInterval(() => void ping(), 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const label =
    state === "online" ? "онлайн" : state === "offline" ? "нет связи" : "проверяю";
  const dotColor =
    state === "online"
      ? "var(--gold)"
      : state === "offline"
        ? "var(--danger)"
        : "var(--mute-2)";

  return (
    <span
      className="inline-flex items-center gap-1.5"
      aria-live="polite"
      title={`Сервер: ${label}`}
    >
      <span
        aria-hidden="true"
        className="size-2 rounded-full"
        style={{ backgroundColor: dotColor }}
      />
      <span className="mono hidden text-[10px] uppercase tracking-[0.12em] text-[color:var(--mute-2)] md:inline">
        {label}
      </span>
    </span>
  );
}
