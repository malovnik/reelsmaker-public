
import { useEffect, useState, useTransition } from "react";
import { api, ApiError } from "@/lib/api";

interface Props {
  jobId: string;
  reelId: string;
}

type Status = "loading" | "ready" | "error" | "missing";

export function CaptionsEditor({ jobId, reelId }: Props) {
  const [content, setContent] = useState("");
  const [saved, setSaved] = useState("");
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();
  const [savedFlash, setSavedFlash] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getReelSubtitles(jobId, reelId)
      .then((txt) => {
        if (cancelled) return;
        setContent(txt);
        setSaved(txt);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setStatus("missing");
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, reelId]);

  const isDirty = content !== saved;

  const onSave = () => {
    setError(null);
    startSaving(async () => {
      try {
        await api.updateReelSubtitles(jobId, reelId, content);
        setSaved(content);
        setSavedFlash(true);
        setTimeout(() => setSavedFlash(false), 1500);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    });
  };

  if (status === "loading") {
    return (
      <div className="text-[12px] text-[color:var(--mute-2)]">
        Загружаю субтитры...
      </div>
    );
  }

  if (status === "missing") {
    return (
      <div className="text-[12px] text-[color:var(--mute-2)]">
        У этого рилса ещё нет ASS-субтитров.
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="text-[12px] text-[color:var(--danger)]">
        Не получилось загрузить субтитры: {error}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        spellCheck={false}
        className="h-96 w-full resize-y rounded-md border border-[color:var(--line)] bg-[color:var(--ink-2)] p-3 font-mono text-[11px] leading-relaxed text-[color:var(--paper)] focus:border-[color:var(--gold)] focus:outline-none"
      />
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={!isDirty || saving}
          onClick={onSave}
          className="btn btn-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? "Сохраняю..." : "Сохранить"}
        </button>
        {isDirty && !saving && (
          <span className="text-[11px] text-[color:var(--mute-2)]">
            Не сохранено
          </span>
        )}
        {savedFlash && !isDirty && (
          <span className="text-[11px] text-[color:var(--mute-2)]">
            Сохранено
          </span>
        )}
        {error && (
          <span className="text-[11px] text-[color:var(--danger)]">{error}</span>
        )}
      </div>
      <p className="text-[11px] leading-snug text-[color:var(--mute-2)]">
        Формат ASS. Изменения применятся, если пересобрать рендер вручную —
        субтитры записаны в <code>{`<job>/subs/${reelId}.ass`}</code>.
      </p>
    </div>
  );
}
