import { useLoaderData } from "react-router-dom";
import {
  api,
  type ModelsInfo,
  type VisionSettingsResponse,
} from "@/lib/api";
import { MoondreamSettings } from "@/components/MoondreamSettings";

interface ModelsLoaderData {
  info: ModelsInfo | null;
  vision: VisionSettingsResponse | null;
}

export async function loader(): Promise<ModelsLoaderData> {
  const [info, vision] = await Promise.all([
    api.models().catch(() => null),
    api.getVisionSettings().catch(() => null),
  ]);
  return { info, vision };
}

export default function ModelsPage() {
  const { info, vision } = useLoaderData() as ModelsLoaderData;

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Модели и провайдеры
        </h1>
        <p className="page-subtitle">
          Ключи API задаются в файле{" "}
          <code className="rounded bg-[color:var(--surface-sunken)] px-1 py-0.5 font-mono text-[12px]">
            .env
          </code>
          . После изменения — перезапусти сервер командой{" "}
          <code className="rounded bg-[color:var(--surface-sunken)] px-1 py-0.5 font-mono text-[12px]">
            ./run.sh
          </code>
          .
        </p>
      </header>

      {!info ? (
        <div className="rounded-lg border border-[color:var(--danger)] bg-[color:var(--danger)]/10 p-4 text-sm text-[color:var(--danger)]">
          Сервер Reelibra не отвечает. Запусти{" "}
          <code className="font-mono">./run.sh</code> и обнови страницу.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <Block
            title="Языковые модели"
            items={{
              gemini: info.defaults.gemini,
              anthropic: info.defaults.anthropic,
              openai: info.defaults.openai,
              zhipu: info.defaults.zhipu,
            }}
            active={info.available_providers}
          />
          <Block
            title="Распознавание речи"
            items={{
              mlx_whisper: info.defaults.mlx_whisper,
              deepgram: info.defaults.deepgram,
            }}
            active={info.available_transcribers}
          />
          {vision ? (
            <MoondreamSettings initial={vision} />
          ) : (
            <section className="surface-card p-5 md:col-span-2">
              <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
                Визуальный анализ (Moondream 2)
              </h2>
              <p className="text-sm text-[color:var(--danger)]">
                Настройки визуального анализа не загрузились. Перезапусти
                Reelibra (<code className="font-mono">./run.sh</code>) и обнови
                страницу.
              </p>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function Block({
  title,
  items,
  active,
}: {
  title: string;
  items: Record<string, string | undefined>;
  active: string[];
}) {
  return (
    <section className="surface-card p-5">
      <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
        {title}
      </h2>
      <dl className="flex flex-col gap-3">
        {Object.entries(items).map(([key, value]) => {
          const enabled = active.includes(key);
          return (
            <div key={key} className="flex items-start gap-3">
              <span
                className={`mt-1 size-2 shrink-0 rounded-full ${
                  enabled
                    ? "bg-[color:var(--success)]"
                    : "bg-[color:var(--border-default)]"
                }`}
                aria-hidden="true"
              />
              <div className="flex flex-1 flex-col">
                <dt className="text-sm text-[color:var(--text-primary)]">
                  {key}
                </dt>
                <dd className="font-mono text-xs text-[color:var(--text-muted)]">
                  {value ?? "—"}{" "}
                  {!enabled && (
                    <span className="text-[color:var(--text-disabled)]">
                      (ключ не задан)
                    </span>
                  )}
                </dd>
              </div>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
