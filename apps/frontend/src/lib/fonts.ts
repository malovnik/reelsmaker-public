/**
 * Шрифты дизайн-системы 色の道 (самурайский брендбук) — self-host через @fontsource.
 *
 * Side-effect модуль: импортируется один раз в main.tsx. Грузит только нужные
 * веса и subset'ы (latin + cyrillic; Japanese у Noto идёт в base-файле).
 *
 * Роли (CSS-переменные в globals.css):
 *   --font-display → Noto Serif JP (заголовки, золото) — 400, 700
 *   --font-body    → Manrope variable (текст/body) — wght 400–700
 *   --font-mono    → JetBrains Mono variable (мета/технический)
 *   --font-pixel   → Press Start 2P (пиксельные микро-теги) — 400
 */

// Display — Noto Serif JP (latin + japanese в base, cyrillic отдельным subset'ом)
import "@fontsource/noto-serif-jp/400.css";
import "@fontsource/noto-serif-jp/700.css";
import "@fontsource/noto-serif-jp/cyrillic-400.css";
import "@fontsource/noto-serif-jp/cyrillic-700.css";

// Body — Manrope variable (один файл покрывает весь диапазон весов)
import "@fontsource-variable/manrope/index.css";

// Mono — JetBrains Mono variable
import "@fontsource-variable/jetbrains-mono/index.css";

// Pixel — Press Start 2P (latin + cyrillic)
import "@fontsource/press-start-2p/400.css";
import "@fontsource/press-start-2p/cyrillic-400.css";
