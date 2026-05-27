
import type { ArtifactRead } from "@/lib/api";

interface Props {
  jobId: string;
  artifacts: ArtifactRead[];
}

const KIND_LABEL: Record<string, string> = {
  proxy: "Рабочая копия",
  transcript: "Транскрипт",
  cleaned_transcript: "Очищенный транскрипт",
  reel_plan: "План рилсов",
  reel_output: "Готовый рилс",
  manifest: "Манифест",
  log: "Лог",
};

export function ArtifactsAccordion({ jobId, artifacts }: Props) {
  if (artifacts.length === 0) return null;

  return (
    <details className="surface-card group overflow-hidden p-0">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-sm text-[color:var(--text-primary)]">
        <span className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
            Промежуточные артефакты
          </span>
          <span className="font-mono text-[11px] text-[color:var(--text-muted)]">
            {artifacts.length}
          </span>
        </span>
        <svg
          className="text-[color:var(--text-muted)] transition-transform duration-200 group-open:rotate-180"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </summary>

      <div className="border-t border-[color:var(--border-subtle)]">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] uppercase tracking-[0.1em] text-[color:var(--text-muted)]">
              <th className="px-5 py-2.5 text-left font-medium">Тип</th>
              <th className="px-5 py-2.5 text-left font-medium">Файл</th>
              <th className="px-5 py-2.5 text-left font-medium">Мета</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[color:var(--border-subtle)]">
            {artifacts.map((a) => (
              <tr
                key={a.id}
                className="transition-colors hover:bg-[color:var(--surface-sunken)]"
              >
                <td className="px-5 py-2.5">
                  <span className="rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 py-0.5 text-[color:var(--text-secondary)]">
                    {KIND_LABEL[a.kind] ?? a.kind}
                  </span>
                </td>
                <td className="px-5 py-2.5">
                  <a
                    href={buildFileUrl(jobId, a.path)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-[color:var(--text-primary)] transition-colors hover:text-[color:var(--accent-primary)]"
                  >
                    {a.path}
                  </a>
                </td>
                <td className="px-5 py-2.5 text-[color:var(--text-muted)]">
                  {Object.keys(a.meta).length > 0
                    ? JSON.stringify(a.meta).slice(0, 80)
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function buildFileUrl(jobId: string, relativePath: string): string {
  const parts = relativePath.split("/").filter(Boolean);
  if (parts.length < 2)
    return `/api/v1/files/${jobId}/log/${encodeURIComponent(relativePath)}`;
  const [kind, ...rest] = parts;
  const name = rest.join("/");
  return `/api/v1/files/${jobId}/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`;
}
