import { BrandKitClient } from "@/components/settings/BrandKitClient";

export default function BrandKitPage() {
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Фирменные стили
        </h1>
        <p className="page-subtitle">
          Сохрани цвета, шрифт и логотип — потом их можно будет подключить
          к субтитрам и пост-продакшн пресетам. Пока данные хранятся локально
          в браузере.
        </p>
      </header>
      <BrandKitClient />
    </div>
  );
}
