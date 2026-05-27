import { useLoaderData } from "react-router-dom";
import {
  api,
  type PostProductionPreset,
  type VideoAsset,
} from "@/lib/api";
import { PostProductionSettingsClient } from "@/components/PostProductionSettingsClient";

interface PostProdLoaderData {
  assets: VideoAsset[];
  presets: PostProductionPreset[];
}

export async function loader(): Promise<PostProdLoaderData> {
  try {
    const [assets, presets] = await Promise.all([
      api.listAssets(),
      api.listPostProductionPresets(),
    ]);
    return { assets, presets };
  } catch {
    return { assets: [], presets: [] };
  }
}

export default function PostProductionSettingsPage() {
  const { assets, presets } = useLoaderData() as PostProdLoaderData;
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="page-h1">
          Пост-продакшн
        </h1>
        <p className="page-subtitle">
          Склейка интро и аутро, нормализация громкости по стандарту
          вещания, зум-эффекты с отслеживанием лица. Применится к нарезкам,
          у которых выбран пресет.
        </p>
      </header>

      <PostProductionSettingsClient
        initialAssets={assets}
        initialPresets={presets}
      />
    </div>
  );
}
