
import { useCallback, useEffect, useState, useTransition } from "react";

interface ConnectionDetail {
  platform: string;
  external_account_name: string | null;
  external_account_id: string | null;
  expires_at: string | null;
}

export function ConnectionsSettings() {
  const [youtube, setYoutube] = useState<ConnectionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const resp = await fetch("/api/v1/connections/youtube/status", {
        cache: "no-store",
      });
      if (resp.status === 200) {
        const data = (await resp.json()) as ConnectionDetail | null;
        setYoutube(data);
      } else {
        setYoutube(null);
      }
    } catch {
      setYoutube(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  function handleConnect() {
    startTransition(async () => {
      setMessage(null);
      try {
        const resp = await fetch("/api/v1/connections/youtube/connect", {
          method: "POST",
        });
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          setMessage(
            body?.detail ??
              `Не удалось запустить OAuth: ${resp.status} ${resp.statusText}`,
          );
          return;
        }
        const data = (await resp.json()) as { authorization_url: string };
        window.location.href = data.authorization_url;
      } catch (exc) {
        setMessage(`Ошибка: ${(exc as Error).message}`);
      }
    });
  }

  function handleDisconnect() {
    startTransition(async () => {
      setMessage(null);
      try {
        const resp = await fetch("/api/v1/connections/youtube", {
          method: "DELETE",
        });
        if (!resp.ok && resp.status !== 404) {
          setMessage(`Ошибка ${resp.status}: не удалось отключить`);
          return;
        }
        await refreshStatus();
      } catch (exc) {
        setMessage(`Ошибка: ${(exc as Error).message}`);
      }
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="surface-card p-6">
        <div className="divider mb-4">YouTube Shorts</div>
        {loading ? (
          <div className="text-sm text-[color:var(--text-muted)]">
            Проверяю состояние подключения…
          </div>
        ) : youtube ? (
          <div className="flex flex-col gap-4">
            <div>
              <div className="mono micro mute mb-1">канал</div>
              <div className="display-serif text-2xl">
                {youtube.external_account_name ?? "—"}
              </div>
              {youtube.external_account_id ? (
                <div className="mono text-[12px] text-[color:var(--text-muted)]">
                  {youtube.external_account_id}
                </div>
              ) : null}
            </div>
            {youtube.expires_at ? (
              <div className="text-sm text-[color:var(--text-secondary)]">
                Access token истекает:{" "}
                {new Date(youtube.expires_at).toLocaleString("ru-RU")}
              </div>
            ) : null}
            <div className="flex gap-3">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={handleDisconnect}
              >
                Отключить
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-[color:var(--text-secondary)]">
              Подключи YouTube канал чтобы публиковать Shorts напрямую. Ты
              будешь перенаправлен на страницу Google, где разрешишь доступ
              к загрузке видео.
            </p>
            <button
              type="button"
              className="btn btn-primary self-start"
              onClick={handleConnect}
            >
              Подключить YouTube
            </button>
            <p className="text-[12px] text-[color:var(--text-muted)]">
              Требуется <code>YOUTUBE_CLIENT_ID</code> и{" "}
              <code>YOUTUBE_CLIENT_SECRET</code> в <code>.env</code>. Создай
              OAuth2 credentials в{" "}
              <a
                href="https://console.cloud.google.com/apis/credentials"
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-2 hover:text-[color:var(--text-primary)]"
              >
                Google Cloud Console
              </a>
              . Redirect URI:{" "}
              <code>http://localhost:8000/api/v1/connections/youtube/callback</code>
              .
            </p>
          </div>
        )}
      </section>

      <section className="surface-card p-6">
        <div className="divider mb-4">Instagram Reels</div>
        <p className="text-sm text-[color:var(--text-secondary)]">
          Подключение Instagram реализуется в следующей фазе: нужен Facebook
          Business аккаунт и ручная проверка App Review. Пока пропускаем.
        </p>
      </section>

      {message ? (
        <div className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4 text-sm">
          {message}
        </div>
      ) : null}
    </div>
  );
}
