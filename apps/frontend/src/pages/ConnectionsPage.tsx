import { useSearchParams } from "react-router-dom";
import { ConnectionsSettings } from "@/components/ConnectionsSettings";

export default function ConnectionsPage() {
  const [searchParams] = useSearchParams();
  const connected = searchParams.get("connected");
  const error = searchParams.get("error");
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Аккаунты публикации
        </h1>
        <p className="page-subtitle">
          Подключи каналы YouTube и Instagram чтобы публиковать рилсы
          напрямую из Reelibra. Токены хранятся локально в{" "}
          <code className="rounded bg-[color:var(--surface-sunken)] px-1 py-0.5 font-mono text-[12px]">
            data/videomaker.db
          </code>
          , на серверы не уходят.
        </p>
      </header>

      {connected === "youtube" ? (
        <div className="rounded-lg border border-[color:var(--success)] bg-[color:var(--success)]/10 p-4 text-sm text-[color:var(--success)]">
          YouTube подключён. Теперь можно планировать публикации из карточки
          рилса или раздела &laquo;Расписание&raquo;.
        </div>
      ) : null}
      {error ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-4 text-sm text-[color:var(--danger)]">
          Не удалось подключить аккаунт: {error}
        </div>
      ) : null}

      <ConnectionsSettings />
    </div>
  );
}
