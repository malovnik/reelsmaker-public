import { ScheduleClient } from "@/components/schedule/ScheduleClient";

export default function SchedulePage() {
  return (
    <main className="page-shell">
      <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Расписание публикаций
        </h1>
        <p className="page-subtitle">
          Запланированные посты на YouTube Shorts и Instagram Reels. Worker
          сканирует очередь раз в минуту и загружает готовые записи.
        </p>
      </header>

      <ScheduleClient />
      </div>
    </main>
  );
}
