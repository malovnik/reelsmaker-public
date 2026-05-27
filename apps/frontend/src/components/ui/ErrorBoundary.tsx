import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Button } from "./Button";

export interface ErrorBoundaryProps {
  children: ReactNode;
  /** Кастомный fallback. Получает ошибку и функцию сброса. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
  /** Колбэк логирования (Sentry и т.п.). */
  onError?: (error: Error, info: ErrorInfo) => void;
  /** Действие кнопки «На главную» (по умолчанию переход на /). */
  onGoHome?: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Классовый Error Boundary. Экран «Клинок затупился» в самурайском стиле:
 * иероглиф 侍 (copper), display-заголовок, точечная --danger-линия, reset.
 * Тех-детали — только в dev. Чистая презентация.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  reset = () => this.setState({ error: null });

  handleGoHome = () => {
    if (this.props.onGoHome) {
      this.props.onGoHome();
    } else if (typeof window !== "undefined") {
      window.location.href = "/";
    }
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);

    const isDev = import.meta.env?.DEV ?? false;

    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 py-16 text-center">
        <div
          aria-hidden="true"
          className="font-[family-name:var(--font-display)] text-6xl leading-none text-[var(--copper,var(--ember))] opacity-70"
        >
          侍
        </div>

        <h1 className="mt-6 font-[family-name:var(--font-display)] text-2xl font-semibold text-[var(--paper)]">
          Клинок затупился
        </h1>

        <div className="mx-auto mt-3 h-px w-24 bg-[var(--danger)]" aria-hidden="true" />

        <p className="mt-4 max-w-md text-[0.9375rem] leading-relaxed text-[var(--mute-2)]">
          Экран не смог отрисоваться. Это не вы — что-то в приложении. Данные целы.
        </p>

        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Button variant="primary" onClick={this.reset}>
            Попробовать снова
          </Button>
          <Button variant="ghost" onClick={this.handleGoHome}>
            На главную
          </Button>
        </div>

        {isDev && (
          <details className="mt-8 w-full max-w-lg text-left">
            <summary className="cursor-pointer font-[family-name:var(--font-mono)] text-[0.75rem] uppercase tracking-[0.1em] text-[var(--mute)]">
              Технические детали (только dev)
            </summary>
            <pre className="mt-2 overflow-auto rounded-none border border-[var(--line-soft)] bg-[var(--ink)] p-3 text-[0.75rem] leading-snug text-[var(--mute-2)]">
              {error.stack ?? error.message}
            </pre>
          </details>
        )}
      </div>
    );
  }
}
