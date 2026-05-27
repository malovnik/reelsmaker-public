/**
 * Извлекает первый кадр видео-файла на клиенте без загрузки на сервер.
 *
 * Создаёт hidden <video> из Object URL, ждёт loadedmetadata + seeked,
 * рисует в <canvas> с maxWidth пропорциональной height, возвращает
 * JPEG data-URL.
 *
 * @param file — выбранный File из <input type="file">
 * @param timeSec — момент видео для кадра (default 0.5с, clamped к duration)
 * @param maxWidth — ширина canvas'а в пикселях (default 480 — достаточно для preview)
 * @returns data-URL ("data:image/jpeg;base64,...") или null если не удалось
 */
export async function extractVideoThumbnail(
  file: File,
  timeSec: number = 0.5,
  maxWidth: number = 480,
): Promise<string | null> {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return null;
  }

  const url = URL.createObjectURL(file);
  try {
    const video = document.createElement("video");
    video.src = url;
    video.muted = true;
    video.playsInline = true;
    video.preload = "metadata";
    video.crossOrigin = "anonymous";

    await new Promise<void>((resolve, reject) => {
      const onLoaded = () => {
        cleanup();
        resolve();
      };
      const onError = () => {
        cleanup();
        reject(new Error("video metadata load failed"));
      };
      const cleanup = () => {
        video.removeEventListener("loadedmetadata", onLoaded);
        video.removeEventListener("error", onError);
      };
      video.addEventListener("loadedmetadata", onLoaded);
      video.addEventListener("error", onError);
    });

    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    const target = duration > 0
      ? Math.max(0, Math.min(timeSec, Math.max(0.1, duration - 0.1)))
      : 0;
    video.currentTime = target;

    await new Promise<void>((resolve, reject) => {
      const onSeeked = () => {
        cleanup();
        resolve();
      };
      const onError = () => {
        cleanup();
        reject(new Error("video seek failed"));
      };
      const cleanup = () => {
        video.removeEventListener("seeked", onSeeked);
        video.removeEventListener("error", onError);
      };
      video.addEventListener("seeked", onSeeked);
      video.addEventListener("error", onError);
    });

    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (vw === 0 || vh === 0) return null;

    const canvas = document.createElement("canvas");
    const ratio = vh / vw;
    canvas.width = maxWidth;
    canvas.height = Math.round(maxWidth * ratio);

    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return canvas.toDataURL("image/jpeg", 0.85);
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Читает image-File как data-URL. Используется для пользовательского
 * «образца кадра» в редакторе пресетов.
 */
export function readImageFileAsDataUrl(file: File): Promise<string | null> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      resolve(typeof result === "string" ? result : null);
    };
    reader.onerror = () => resolve(null);
    reader.readAsDataURL(file);
  });
}
