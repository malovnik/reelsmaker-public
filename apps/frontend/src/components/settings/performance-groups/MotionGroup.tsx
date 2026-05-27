
import {
  Group,
  NumberRow,
  SliderRow,
  SwitchRow,
} from "@/components/settings-shared";
import type { GroupProps } from "./types";

interface Props extends GroupProps {
  onReset: () => void;
}

export function MotionGroup({ values, update, onReset }: Props) {
  return (
    <Group title="Движение кадра (punch-in zoom + Ken Burns)">
      <SwitchRow
        id="punch_in_zoom_enabled"
        label="Наезд камеры на акцентах"
        hint="На моменты эмоциональных акцентов добавляется короткий zoom-in. Усиливает драматургию. Стандарт: включено — но только если в UploadWizard разрешён зум."
        checked={values.punch_in_zoom_enabled}
        onChange={(v) => update("punch_in_zoom_enabled", v)}
      />
      {values.punch_in_zoom_enabled && (
        <>
          <SliderRow
            id="punch_in_zoom_scale"
            label="Масштаб наезда"
            hint="Во сколько раз увеличивается кадр на акценте. 1,05 — едва заметно, 1,15 — выраженно. Стандарт: 1,08."
            value={values.punch_in_zoom_scale}
            min={1.0}
            max={1.15}
            step={0.01}
            onChange={(v) => update("punch_in_zoom_scale", v)}
          />
          <SliderRow
            id="punch_in_zoom_probability"
            label="Вероятность срабатывания"
            hint="Не каждый акцент получает зум — вероятность защищает от перегруза. Стандарт: 0,30."
            value={values.punch_in_zoom_probability}
            min={0.0}
            max={0.6}
            step={0.05}
            onChange={(v) => update("punch_in_zoom_probability", v)}
          />
          <NumberRow
            id="punch_in_zoom_hold_ms"
            label="Длительность наезда (мс)"
            hint="Как долго держится зум до возврата. Стандарт: 600 мс — воспринимается как акцент, не резкий."
            value={values.punch_in_zoom_hold_ms}
            min={100}
            max={1500}
            step={50}
            unit="мс"
            onChange={(v) => update("punch_in_zoom_hold_ms", v)}
          />
        </>
      )}
      <SwitchRow
        id="ken_burns_drift_enabled"
        label="Медленный дрейф кадра (Ken Burns)"
        hint="На статичных шотах добавляется едва заметное движение — зритель остаётся в видео. Стандарт: выключено для talking-head, включается advisor'ом для кадров без движения."
        checked={values.ken_burns_drift_enabled}
        onChange={(v) => update("ken_burns_drift_enabled", v)}
      />
      {values.ken_burns_drift_enabled && (
        <>
          <SliderRow
            id="ken_burns_scale_per_sec"
            label="Скорость дрейфа"
            hint="Насколько быстро растёт масштаб за секунду. 0,001 — статика, 0,01 — заметное движение. Стандарт: 0,002."
            value={values.ken_burns_scale_per_sec}
            min={0.001}
            max={0.01}
            step={0.0005}
            onChange={(v) => update("ken_burns_scale_per_sec", v)}
          />
          <SliderRow
            id="ken_burns_max_scale"
            label="Максимальный масштаб дрейфа"
            hint="Когда дрейф дойдёт до этого значения — движение останавливается. Стандарт: 1,025."
            value={values.ken_burns_max_scale}
            min={1.005}
            max={1.05}
            step={0.005}
            onChange={(v) => update("ken_burns_max_scale", v)}
          />
        </>
      )}
      <SwitchRow
        id="face_tracker_enabled"
        label="Face tracker (MediaPipe) · экспериментально, opt-in"
        hint="Детекция лица для face-centered base crop. Нужно только если глобальный fit=fill и важно удержать лицо в кадре. По умолчанию OFF (безопасный center-crop) — letterbox / manual / split-вручную работают без этого. Экспериментальная фича: детект вынесен в отдельный процесс с hard-таймаутом, при зависании/ошибке рендер сам падает на center-crop и продолжается."
        checked={values.face_tracker_enabled ?? false}
        onChange={(v) => update("face_tracker_enabled", v)}
      />
      <button
        type="button"
        onClick={onReset}
        className="self-start text-xs text-[color:var(--accent-primary)] underline-offset-2 hover:underline"
      >
        Вернуть стандартные значения
      </button>
    </Group>
  );
}
