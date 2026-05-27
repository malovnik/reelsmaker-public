
import { useState } from "react";
import type { AutoAnalyzeResponse } from "@/lib/api";

/**
 * T11.4 — AutoConfigSummary card.
 *
 * Показывает пользователю решения которые Automatic Mode принял для его
 * видео. Confidence + evidence chain + warnings. Кнопка «Запустить»
 * применяет config, «Детали» раскрывает полный evidence log.
 */
export function AutoConfigSummary({
  data,
  onAccept,
  onSwitchToManual,
}: {
  data: AutoAnalyzeResponse;
  onAccept: () => void;
  onSwitchToManual: () => void;
}) {
  const [showDetails, setShowDetails] = useState(false);

  const confidencePct = Math.round(data.meta_confidence * 100);
  const confidenceClass =
    confidencePct >= 70
      ? "text-[color:var(--success)]"
      : confidencePct >= 40
      ? "text-[color:var(--warning)]"
      : "text-rose-700";

  const wps = Number(data.audio_features.wps ?? 0);
  const pitch = Number(data.audio_features.pitch_std_hz ?? 0);
  const snr = Number(data.audio_features.snr_db ?? 0);
  const duration = Number(data.audio_features.total_duration_sec ?? 0);

  return (
    <div className="rounded-2xl border border-[color:var(--line-soft)] bg-[color:var(--ink-2)]/60 p-6 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-stone-900">
            Автоматический режим проанализировал видео
          </h3>
          <p className={`text-sm ${confidenceClass}`}>
            Уверенность: {confidencePct}%
            {data.llm_fallback_applied && (
              <span className="ml-2 text-stone-500 text-xs">
                · уточнено через Gemini
              </span>
            )}
          </p>
        </div>
        <div className="text-right text-xs text-stone-500">
          {formatDuration(duration)} · {data.audio_features.num_words} слов
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <Metric label="Темп речи" value={`${wps.toFixed(1)} слов/сек`} />
        <Metric
          label="Эмоциональность"
          value={`pitch std ${pitch.toFixed(0)} Hz`}
        />
        <Metric label="Качество аудио" value={`SNR ${snr.toFixed(0)} dB`} />
        <Metric
          label="Rhythm CV"
          value={String(data.audio_features.rhythm_cv ?? "—")}
        />
      </div>

      <div className="border-t border-[color:var(--line-soft)] pt-4">
        <h4 className="text-sm font-medium text-stone-700 mb-2">
          Принятые решения
        </h4>
        <ul className="space-y-1.5 text-sm">
          <DecisionRow
            label="Стиль монтажа"
            value={pacingLabel(data.pacing_profile)}
          />
          <DecisionRow
            label="Склейка к ритму"
            value={snapLabel(data.snap_strategy)}
          />
          <DecisionRow
            label="Свобода композиции"
            value={composerLabel(data.composer_strategy)}
          />
          <DecisionRow
            label="Удержание после фраз"
            value={
              data.punchline_pause_enabled
                ? `включено, ${data.punchline_hold_after_sec.toFixed(2)} сек`
                : "выключено"
            }
          />
          <DecisionRow
            label="Наезд камеры на акценты"
            value={
              data.punch_in_zoom_enabled
                ? `включено, ${data.punch_in_zoom_scale.toFixed(2)}×, вероятность ${Math.round(data.punch_in_zoom_probability * 100)}%`
                : "выключено"
            }
          />
          <DecisionRow
            label="Плавный дрифт (Ken Burns)"
            value={data.ken_burns_drift_enabled ? "включено" : "выключено"}
          />
          <DecisionRow
            label="Сжатие пауз"
            value={
              data.pause_compression_enabled
                ? `порог ${data.pause_compression_threshold_sec.toFixed(2)}с, оставить ${data.pause_compression_keep_sec.toFixed(2)}с`
                : "выключено"
            }
          />
          <DecisionRow
            label="Удаление слов-паразитов"
            value={
              data.filler_words_removal_enabled ? "включено" : "выключено"
            }
          />
        </ul>
      </div>

      {data.warnings.length > 0 && (
        <div className="rounded-lg bg-[color:var(--warning)]/10 border border-[color:var(--warning)]/30 p-3 space-y-1">
          {data.warnings.map((w, i) => (
            <p key={i} className="text-xs text-[color:var(--warning)]">
              ⚠ {w}
            </p>
          ))}
        </div>
      )}

      {showDetails && (
        <div className="border-t border-[color:var(--line-soft)] pt-4 space-y-2">
          <h4 className="text-sm font-medium text-stone-700">
            Полный evidence chain ({data.decisions.length} решений)
          </h4>
          <ul className="space-y-2 text-xs max-h-80 overflow-y-auto">
            {data.decisions.map((d, i) => (
              <li key={i} className="border border-[color:var(--line-soft)] rounded p-2">
                <div className="flex justify-between">
                  <span className="font-medium text-stone-900">
                    {d.parameter}
                  </span>
                  <span
                    className={
                      d.source === "safety_clamp"
                        ? "text-rose-700"
                        : d.source === "llm"
                        ? "text-[color:var(--gold)]"
                        : "text-stone-500"
                    }
                  >
                    {d.source} · {Math.round(d.confidence * 100)}%
                  </span>
                </div>
                <div className="text-stone-700">{String(d.value)}</div>
                <div className="text-stone-500">{d.reasoning}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex gap-3 pt-2">
        <button
          type="button"
          onClick={onAccept}
          className="flex-1 bg-stone-900 hover:bg-stone-800 text-stone-50 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors"
        >
          Запустить с этими настройками
        </button>
        <button
          type="button"
          onClick={() => setShowDetails((v) => !v)}
          className="px-4 py-2.5 text-sm text-stone-600 hover:text-stone-900 border border-[color:var(--line-soft)] rounded-lg transition-colors"
        >
          {showDetails ? "Скрыть детали" : "Детали"}
        </button>
        <button
          type="button"
          onClick={onSwitchToManual}
          className="px-4 py-2.5 text-sm text-stone-600 hover:text-stone-900 border border-[color:var(--line-soft)] rounded-lg transition-colors"
        >
          Настроить вручную
        </button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white border border-[color:var(--line-soft)] p-3">
      <div className="text-xs text-stone-500 mb-0.5">{label}</div>
      <div className="text-sm font-medium text-stone-900">{value}</div>
    </div>
  );
}

function DecisionRow({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex justify-between gap-4 py-0.5">
      <span className="text-stone-600">{label}</span>
      <span className="text-stone-900 text-right">{value}</span>
    </li>
  );
}

function pacingLabel(profile: string): string {
  const map: Record<string, string> = {
    dynamic: "Динамичный (быстрые cuts)",
    balanced: "Сбалансированный",
    mkbhd_clean: "Чистый (MKBHD-style)",
    documentary: "Документальный (долгие планы)",
  };
  return map[profile] ?? profile;
}

function snapLabel(strategy: string): string {
  const map: Record<string, string> = {
    beat: "К музыкальным битам",
    onset: "К началу слогов (речь)",
    both: "Комбинированная",
    off: "Выключена",
  };
  return map[strategy] ?? strategy;
}

function composerLabel(strategy: string): string {
  const map: Record<string, string> = {
    tight_context: "Сохранять контекст сцены",
    balanced: "Сбалансированная",
    thematic_free: "Свободная тематическая",
  };
  return map[strategy] ?? strategy;
}

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec.toFixed(0)} сек`;
  const minutes = Math.floor(sec / 60);
  const seconds = Math.round(sec % 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
