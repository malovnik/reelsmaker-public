import { useLoaderData } from "react-router-dom";
import { schedulerApi } from "@/lib/api";
import { AccountProfilesDashboard } from "@/components/scheduler/AccountProfilesDashboard";
import type { AccountProfile, PublerAccount } from "@/lib/api/scheduler";

interface AccountsLoaderData {
  accounts: PublerAccount[];
  profiles: AccountProfile[];
  error: string | null;
}

export async function loader(): Promise<AccountsLoaderData> {
  try {
    const [accounts, profiles] = await Promise.all([
      schedulerApi.listPublerAccounts(),
      schedulerApi.listProfiles(),
    ]);
    return { accounts, profiles, error: null };
  } catch (exc) {
    return {
      accounts: [],
      profiles: [],
      error: exc instanceof Error ? exc.message : String(exc),
    };
  }
}

export default function AccountsPage() {
  const { accounts, profiles, error } = useLoaderData() as AccountsLoaderData;
  return (
    <main className="page-shell">
      <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Профили аккаунтов
        </h1>
        <p className="page-subtitle">
          Для каждого подключённого в Publer аккаунта можно задать язык, тон,
          аудиторию, стоп-слова и базовые хэштеги. Генератор описаний использует
          эти параметры как контекст перед выбором слов.
        </p>
      </header>

      <AccountProfilesDashboard
        initialAccounts={accounts}
        initialProfiles={profiles}
        initialError={error}
      />
      </div>
    </main>
  );
}
