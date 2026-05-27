import { useLoaderData } from "react-router-dom";
import { api, type PromptPayload } from "@/lib/api";
import { PromptsEditorClient } from "@/components/PromptsEditorClient";

export async function loader(): Promise<PromptPayload[]> {
  try {
    const data = await api.listPrompts();
    return data.prompts;
  } catch {
    return [];
  }
}

export default function PromptsPage() {
  const prompts = useLoaderData() as PromptPayload[];
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Редактор промптов
        </h1>
        <p className="page-subtitle">
          Системные инструкции для этапов анализа. Изменения применятся к
          следующим нарезкам без перезапуска сервера. Чтобы откатить к
          дефолтам — удали строку из базы данных (таблица{" "}
          <code className="rounded bg-[color:var(--surface-sunken)] px-1 py-0.5 font-mono text-[12px]">
            prompt_settings
          </code>
          ).
        </p>
      </header>
      <PromptsEditorClient initial={prompts} />
    </div>
  );
}
