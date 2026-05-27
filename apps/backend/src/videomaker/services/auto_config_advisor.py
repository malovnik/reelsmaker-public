"""T11.2 — Automatic Mode rule engine (робот-монтажёр policy layer).

Принимает AudioProfile от `audio_analyzer` и возвращает AutoConfig —
решения по всем 25+ параметрам pipeline для этого конкретного видео.
Заменяет глобальные defaults в runtime_settings на per-video optimal.

Архитектура (hybrid из research `automatic-mode-2026.md`):
- 25 hard-coded правил (matrix WPS × pitch_std → pacing_profile)
- SAFETY_LIMITS circuit breaker — даже если rule tree вернул
  экстремальное значение, оно clamp'ится к safe range
- compute_meta_confidence — overall уверенность 0..1
- generate_warnings — human-readable предупреждения для UI
- Gemini Flash Lite fallback (T11.5) при confidence < 0.4 — отдельно

Интерфейс:
    from videomaker.services.auto_config_advisor import advise_config
    config = advise_config(audio_profile)
    # → AutoConfig с 25 decisions + confidence + evidence + warnings

Manual mode: если PerformanceSettings.pipeline_mode == "manual", advisor
не вызывается, используются текущие настройки runtime.

Цель автономности: 85-90% talking-head на ru/en без user review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from videomaker.core.logging import get_logger
from videomaker.models.audio_profile import AudioProfile

log = get_logger(__name__)


#: Confidence ниже этого порога — fallback на safe defaults, не на LLM.
#: LLM-fallback применяется в pipeline_runner отдельно (T11.5).
CONFIDENCE_FALLBACK_THRESHOLD = 0.4

#: Circuit breaker — даже если rule tree решил 2.0x zoom, clamp к 1.15.
#: Research: research/automatic-mode-2026.md § 7.2.
SAFETY_LIMITS: dict[str, dict[str, float]] = {
    "pause_compression_keep_sec": {"min": 0.15, "max": 0.5},
    "pause_compression_threshold_sec": {"min": 0.2, "max": 2.0},
    "breath_compression_keep_sec": {"min": 0.08, "max": 0.25},
    "breath_compression_threshold_sec": {"min": 0.15, "max": 0.5},
    "punch_in_zoom_scale": {"min": 1.0, "max": 1.15},
    "punch_in_zoom_probability": {"min": 0.0, "max": 0.6},
    "punchline_hold_after_sec": {"min": 0.15, "max": 0.8},
    "onset_snap_max_shift_sec": {"min": 0.02, "max": 0.2},
    "ken_burns_scale_per_sec": {"min": 0.001, "max": 0.01},
    "ken_burns_max_scale": {"min": 1.005, "max": 1.05},
    "coherence_threshold": {"min": 0.3, "max": 0.8},
}


PacingProfile = Literal["dynamic", "balanced", "mkbhd_clean", "documentary"]
SnapStrategyDecision = Literal["beat", "onset", "both", "off"]
ComposerStrategyDecision = Literal["tight_context", "balanced", "thematic_free"]


@dataclass(slots=True)
class DecisionEvidence:
    """Evidence chain для UI summary — почему advisor принял такое решение."""

    parameter: str
    value: float | int | bool | str
    confidence: float
    source: str  # "rule" | "default" | "safety_clamp" | "llm"
    reasoning: str


@dataclass(slots=True)
class AutoConfig:
    """Все decisions робот-монтажёра для этого видео."""

    # === Pacing (главное решение) ===
    pacing_profile: PacingProfile = "balanced"

    # === Audio cleanup ===
    pause_compression_enabled: bool = True
    pause_compression_threshold_sec: float = 0.4
    pause_compression_keep_sec: float = 0.2
    breath_compression_enabled: bool = False
    breath_compression_threshold_sec: float = 0.25
    breath_compression_keep_sec: float = 0.08
    filler_words_removal_enabled: bool = False

    # === Rhythm / cuts ===
    snap_strategy: SnapStrategyDecision = "onset"
    onset_snap_max_shift_sec: float = 0.08
    rhythm_aware_cuts_enabled: bool = False
    rhythm_aware_max_shift_sec: float = 0.15

    # === Punchline ===
    punchline_pause_enabled: bool = True
    punchline_hold_after_sec: float = 0.45

    # === Motion ===
    punch_in_zoom_enabled: bool = False
    punch_in_zoom_scale: float = 1.06
    punch_in_zoom_probability: float = 0.3
    ken_burns_drift_enabled: bool = False
    ken_burns_scale_per_sec: float = 0.003
    ken_burns_max_scale: float = 1.025

    # === Coherence / composer ===
    coherence_threshold: float = 0.5
    composer_strategy: ComposerStrategyDecision = "balanced"

    # === Meta ===
    meta_confidence: float = 0.8
    evidence: list[DecisionEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_llm_fallback: bool = False


def advise_config(
    profile: AudioProfile,
    post_production_config: dict[str, object] | None = None,
) -> AutoConfig:
    """Main entry point — применяет 25 правил к AudioProfile.

    Возвращает AutoConfig с evidence/warnings/confidence. Если confidence
    ниже threshold → ставит requires_llm_fallback=True (caller вызывает
    Gemini Flash Lite advisor отдельно).

    ``post_production_config`` — snapshot post_production_config_json из
    Job. Если пользователь отключил zoom (zoom_enabled=False) в UploadWizard,
    advisor уважает этот master toggle и принудительно ставит
    ``punch_in_zoom_enabled=False`` + ``ken_burns_drift_enabled=False``.

    Никогда не падает — все решения через safe defaults при edge cases.
    """
    cfg = AutoConfig()
    evidence: list[DecisionEvidence] = []

    # Rule 1: Pacing profile — 2D матрица WPS × pitch_std (research секция B).
    cfg.pacing_profile = _decide_pacing_profile(profile, evidence)

    # Rules 2-4: Pause compression по mean_gap / kurtosis.
    _decide_pause_compression(profile, cfg, evidence)

    # Rule 5: Breath compression по rhythm_cv + wps.
    if profile.wps > 3.0 and profile.rhythm_cv < 0.4:
        cfg.breath_compression_enabled = True
        evidence.append(
            DecisionEvidence(
                parameter="breath_compression_enabled",
                value=True,
                confidence=0.75,
                source="rule",
                reasoning=f"fast speech ({profile.wps:.1f} wps) + "
                f"regular rhythm (CV={profile.rhythm_cv:.2f})",
            )
        )

    # Rule 6: Filler removal — только при высокой whisper confidence.
    if profile.whisper_avg_confidence > 0.6 and profile.snr_db > 15:
        cfg.filler_words_removal_enabled = True
        evidence.append(
            DecisionEvidence(
                parameter="filler_words_removal_enabled",
                value=True,
                confidence=0.85,
                source="rule",
                reasoning=f"clean audio (SNR {profile.snr_db:.0f}) + "
                f"reliable transcript ({profile.whisper_avg_confidence:.2f})",
            )
        )

    # Rules 7-8: Snap strategy по rhythm_cv (onset vs beat vs both).
    cfg.snap_strategy = _decide_snap_strategy(profile, evidence)
    if cfg.snap_strategy in {"beat", "both"}:
        cfg.rhythm_aware_cuts_enabled = True
    cfg.onset_snap_max_shift_sec = _decide_onset_window(profile, evidence)

    # Rule 9: Coherence threshold по pitch_std.
    cfg.coherence_threshold = _decide_coherence_threshold(profile, evidence)

    # Rule 10: Composer strategy по pitch + gap_kurtosis + wps.
    cfg.composer_strategy = _decide_composer_strategy(profile, evidence)

    # Rule 11: Punchline hold scales с WPS (медленная речь → длиннее hold).
    cfg.punchline_hold_after_sec = _decide_punchline_hold(profile, evidence)

    # Rules 12-14: Punch-in zoom (включение + scale + probability).
    _decide_punch_in_zoom(profile, cfg, evidence)

    # Rules 15-16: Ken Burns (статичные шоты).
    _decide_ken_burns(profile, cfg, evidence)

    # Apply safety limits.
    _apply_safety_limits(cfg, evidence)

    # T11 master toggles: пользователь отключил zoom/bw в UploadWizard —
    # Auto mode уважает этот ручной выбор. Принудительно гасим motion-эффекты.
    if post_production_config is not None:
        _apply_master_toggles(post_production_config, cfg, evidence)

    # Meta-confidence + warnings.
    cfg.meta_confidence = round(_compute_meta_confidence(profile), 3)
    cfg.warnings = _generate_warnings(profile, cfg)
    cfg.requires_llm_fallback = cfg.meta_confidence < CONFIDENCE_FALLBACK_THRESHOLD

    cfg.evidence = evidence

    log.info(
        "auto_advisor_done",
        pacing=cfg.pacing_profile,
        snap=cfg.snap_strategy,
        composer=cfg.composer_strategy,
        punchline_enabled=cfg.punchline_pause_enabled,
        punch_in=cfg.punch_in_zoom_enabled,
        ken_burns=cfg.ken_burns_drift_enabled,
        filler_removal=cfg.filler_words_removal_enabled,
        meta_confidence=cfg.meta_confidence,
        warnings=len(cfg.warnings),
        llm_fallback=cfg.requires_llm_fallback,
    )
    return cfg


def _decide_pacing_profile(
    profile: AudioProfile, evidence: list[DecisionEvidence]
) -> PacingProfile:
    """2D матрица WPS × pitch_std (research секция B таблица)."""
    wps = profile.wps
    pitch_std = profile.pitch_std_hz

    if pitch_std >= 40:
        if wps < 2.0:
            choice: PacingProfile = "documentary"
        elif wps < 3.5:
            choice = "balanced"
        else:
            choice = "dynamic"
    elif pitch_std >= 20:
        if wps < 2.0:
            choice = "documentary"
        elif wps < 2.8:
            choice = "balanced"
        elif wps < 3.5:
            choice = "mkbhd_clean"
        else:
            choice = "dynamic"
    else:
        choice = "documentary" if wps < 2.8 else "mkbhd_clean"

    evidence.append(
        DecisionEvidence(
            parameter="pacing_profile",
            value=choice,
            confidence=0.85 if profile.wps > 0 else 0.4,
            source="rule",
            reasoning=f"WPS={wps:.1f} × pitch_std={pitch_std:.0f} Hz matrix",
        )
    )
    return choice


def _decide_pause_compression(
    profile: AudioProfile,
    cfg: AutoConfig,
    evidence: list[DecisionEvidence],
) -> None:
    mean_gap = profile.mean_gap_sec
    cfg.pause_compression_enabled = mean_gap > 0.25
    cfg.pause_compression_threshold_sec = max(0.3, mean_gap * 0.7)

    if profile.gap_kurtosis > 3:
        cfg.pause_compression_keep_sec = 0.35
        kurtosis_note = "high kurtosis → preserve semantic pauses"
    elif profile.gap_kurtosis < 1:
        cfg.pause_compression_keep_sec = 0.20
        kurtosis_note = "flat pause distribution → safe to compress"
    else:
        cfg.pause_compression_keep_sec = 0.25
        kurtosis_note = "normal kurtosis"

    evidence.append(
        DecisionEvidence(
            parameter="pause_compression",
            value=f"enabled={cfg.pause_compression_enabled}, "
            f"threshold={cfg.pause_compression_threshold_sec:.2f}s, "
            f"keep={cfg.pause_compression_keep_sec:.2f}s",
            confidence=0.8,
            source="rule",
            reasoning=f"mean_gap={mean_gap:.2f}s, kurtosis={profile.gap_kurtosis:.1f} — {kurtosis_note}",
        )
    )


def _decide_snap_strategy(
    profile: AudioProfile, evidence: list[DecisionEvidence]
) -> SnapStrategyDecision:
    cv = profile.rhythm_cv
    if cv < 0.3:
        choice: SnapStrategyDecision = "beat"
        reason = f"regular rhythm (CV={cv:.2f}) → likely music → beat-snap"
    elif cv < 0.5:
        choice = "both"
        reason = f"mixed rhythm (CV={cv:.2f}) → try onset first, beat fallback"
    elif cv < 0.8:
        choice = "onset"
        reason = f"speech rhythm (CV={cv:.2f}) → onset-snap"
    else:
        choice = "off"
        reason = f"chaotic rhythm (CV={cv:.2f}) → skip snap entirely"

    evidence.append(
        DecisionEvidence(
            parameter="snap_strategy",
            value=choice,
            confidence=0.75,
            source="rule",
            reasoning=reason,
        )
    )
    return choice


def _decide_onset_window(
    profile: AudioProfile, evidence: list[DecisionEvidence]
) -> float:
    if profile.rhythm_cv < 0.25:
        window = 0.08
    elif profile.rhythm_cv > 0.5:
        window = 0.2
    else:
        window = 0.12
    evidence.append(
        DecisionEvidence(
            parameter="onset_snap_max_shift_sec",
            value=window,
            confidence=0.7,
            source="rule",
            reasoning=f"tight window at CV {profile.rhythm_cv:.2f}",
        )
    )
    return window


def _decide_coherence_threshold(
    profile: AudioProfile, evidence: list[DecisionEvidence]
) -> float:
    if profile.pitch_std_hz > 35:
        threshold = 0.35
        reason = "emotional content (high pitch variance) → strict coherence"
    elif profile.pitch_std_hz < 15:
        threshold = 0.25
        reason = "monotone content → relaxed coherence threshold"
    else:
        threshold = 0.5
        reason = "balanced pitch variance"
    evidence.append(
        DecisionEvidence(
            parameter="coherence_threshold",
            value=threshold,
            confidence=0.7,
            source="rule",
            reasoning=reason,
        )
    )
    return threshold


def _decide_composer_strategy(
    profile: AudioProfile, evidence: list[DecisionEvidence]
) -> ComposerStrategyDecision:
    if profile.pitch_std_hz > 40 and profile.wps > 3.0:
        choice: ComposerStrategyDecision = "tight_context"
        reason = "high energy + fast speech → keep tight narrative"
    elif profile.gap_kurtosis > 3:
        choice = "balanced"
        reason = f"narrative pauses (kurtosis {profile.gap_kurtosis:.1f}) → balanced"
    elif profile.wps < 2.0:
        choice = "thematic_free"
        reason = "slow pacing → thematic freedom safe"
    else:
        choice = "balanced"
        reason = "default balanced strategy"

    evidence.append(
        DecisionEvidence(
            parameter="composer_strategy",
            value=choice,
            confidence=0.7,
            source="rule",
            reasoning=reason,
        )
    )
    return choice


def _decide_punchline_hold(
    profile: AudioProfile, evidence: list[DecisionEvidence]
) -> float:
    if profile.wps < 2.0:
        hold = 0.55
    elif profile.wps > 3.5:
        hold = 0.30
    else:
        hold = 0.45
    evidence.append(
        DecisionEvidence(
            parameter="punchline_hold_after_sec",
            value=hold,
            confidence=0.75,
            source="rule",
            reasoning=f"wps={profile.wps:.1f} → hold {hold:.2f}s",
        )
    )
    return hold


def _decide_punch_in_zoom(
    profile: AudioProfile,
    cfg: AutoConfig,
    evidence: list[DecisionEvidence],
) -> None:
    # Включаем только на эмоциональном talking-head.
    talking_head = profile.content_type in {"talking_head", "interview", "unknown"}
    emotional = profile.pitch_std_hz > 25
    cfg.punch_in_zoom_enabled = talking_head and emotional

    if cfg.punch_in_zoom_enabled:
        if profile.wps > 3.5:
            cfg.punch_in_zoom_scale = 1.10
            cfg.punch_in_zoom_probability = 0.45
        elif profile.wps < 2.0:
            cfg.punch_in_zoom_scale = 1.04
            cfg.punch_in_zoom_probability = 0.2
        else:
            cfg.punch_in_zoom_scale = 1.06
            cfg.punch_in_zoom_probability = 0.3

    evidence.append(
        DecisionEvidence(
            parameter="punch_in_zoom",
            value=f"enabled={cfg.punch_in_zoom_enabled}, "
            f"scale={cfg.punch_in_zoom_scale}, p={cfg.punch_in_zoom_probability}",
            confidence=0.75 if cfg.punch_in_zoom_enabled else 0.6,
            source="rule",
            reasoning=f"content={profile.content_type}, "
            f"pitch_std={profile.pitch_std_hz:.0f} Hz, wps={profile.wps:.1f}",
        )
    )


def _decide_ken_burns(
    profile: AudioProfile,
    cfg: AutoConfig,
    evidence: list[DecisionEvidence],
) -> None:
    # Ken Burns для медленного/документального контента.
    cfg.ken_burns_drift_enabled = profile.wps < 2.0 or profile.content_type == "interview"
    if cfg.ken_burns_drift_enabled:
        if profile.wps < 1.5:
            cfg.ken_burns_scale_per_sec = 0.005
        else:
            cfg.ken_burns_scale_per_sec = 0.003
    evidence.append(
        DecisionEvidence(
            parameter="ken_burns_drift",
            value=f"enabled={cfg.ken_burns_drift_enabled}, "
            f"speed={cfg.ken_burns_scale_per_sec}",
            confidence=0.7,
            source="rule",
            reasoning=f"wps={profile.wps:.1f}, content={profile.content_type}",
        )
    )


def _apply_safety_limits(
    cfg: AutoConfig, evidence: list[DecisionEvidence]
) -> None:
    """Clamp values to SAFETY_LIMITS. Adds evidence entry если что-то clamp'нулось."""
    for param, limits in SAFETY_LIMITS.items():
        if not hasattr(cfg, param):
            continue
        value = getattr(cfg, param)
        if not isinstance(value, int | float):
            continue
        clamped = max(limits["min"], min(limits["max"], float(value)))
        if clamped != value:
            setattr(cfg, param, clamped)
            evidence.append(
                DecisionEvidence(
                    parameter=param,
                    value=clamped,
                    confidence=1.0,
                    source="safety_clamp",
                    reasoning=f"clamped from {value} to [{limits['min']}, {limits['max']}]",
                )
            )



def _apply_master_toggles(
    post_production_config: dict[str, object],
    cfg: AutoConfig,
    evidence: list[DecisionEvidence],
) -> None:
    """T11 — Auto mode уважает master toggles пользователя из UploadWizard.

    PostProductionConfig приходит как snapshot post_production_config_json
    с уже применёнными override'ами (enable_zoom/enable_bw из UI).

    Контракт:
    * ``zoom_enabled=False`` → погасить punch_in_zoom + ken_burns drift
    * ``bw_enabled=False`` — уже учтено в post_production snapshot,
      отдельное действие в AutoConfig не нужно.
    * intro/outro отсутствуют в AutoConfig decisions — управляются
      post_production_config напрямую, дублирующая проверка не нужна.
    """
    zoom_enabled = bool(post_production_config.get("zoom_enabled", True))
    if not zoom_enabled:
        if cfg.punch_in_zoom_enabled:
            cfg.punch_in_zoom_enabled = False
            evidence.append(
                DecisionEvidence(
                    parameter="punch_in_zoom_enabled",
                    value=False,
                    confidence=1.0,
                    source="user_master_toggle",
                    reasoning="user disabled zoom in UploadWizard — Auto mode honours master toggle",
                )
            )
        if cfg.ken_burns_drift_enabled:
            cfg.ken_burns_drift_enabled = False
            evidence.append(
                DecisionEvidence(
                    parameter="ken_burns_drift_enabled",
                    value=False,
                    confidence=1.0,
                    source="user_master_toggle",
                    reasoning="user disabled zoom in UploadWizard — Ken Burns drift forced off",
                )
            )


def _compute_meta_confidence(profile: AudioProfile) -> float:
    """Overall уверенность в accepted config. 0.0-1.0."""
    confidence = 1.0

    # SNR fact (плохой mic → advisor ненадёжен)
    if profile.snr_db < 10:
        confidence *= 0.5
    elif profile.snr_db < 18:
        confidence *= 0.8

    # Whisper quality (плохая транскрипция → ненадёжный WPS)
    if profile.whisper_avg_confidence < 0.5 and profile.num_words > 0:
        confidence *= 0.6
    elif profile.whisper_avg_confidence < 0.7 and profile.num_words > 0:
        confidence *= 0.85

    # Duration (мало данных для статистики)
    if profile.total_duration_sec < 120:
        confidence *= 0.7

    # Unknown content type
    if profile.content_type == "unknown":
        confidence *= 0.85

    # Failures в feature extraction
    failure_penalty = max(0.5, 1.0 - 0.1 * len(profile.failures))
    confidence *= failure_penalty

    return round(confidence, 3)


def _generate_warnings(profile: AudioProfile, cfg: AutoConfig) -> list[str]:
    warnings: list[str] = []

    if profile.snr_db < 10:
        warnings.append(
            f"Низкое качество аудио (SNR {profile.snr_db:.0f} dB). "
            "Автоматический режим применит консервативные настройки."
        )
    if profile.whisper_avg_confidence < 0.4 and profile.num_words > 0:
        warnings.append(
            "Качество транскрипции низкое. Удаление слов-паразитов отключено."
        )
    if profile.wps < 0.5 and profile.num_words > 0:
        warnings.append(
            "Очень мало речи в видео. Проверьте что дорожка содержит голос."
        )
    if cfg.meta_confidence < CONFIDENCE_FALLBACK_THRESHOLD:
        warnings.append(
            f"Автоматический режим имеет низкую уверенность "
            f"({cfg.meta_confidence:.0%}). Рекомендуем проверить настройки."
        )
    if profile.failures:
        warnings.append(
            f"Не удалось посчитать: {', '.join(profile.failures)}. "
            "Использованы значения по умолчанию."
        )
    if profile.max_gap_sec > 8.0:
        warnings.append(
            f"Очень длинные паузы в записи (до {profile.max_gap_sec:.1f}s). "
            "Возможно автоподбор параметров недостаточно чувствителен."
        )
    return warnings


__all__ = [
    "CONFIDENCE_FALLBACK_THRESHOLD",
    "SAFETY_LIMITS",
    "AutoConfig",
    "DecisionEvidence",
    "advise_config",
]
