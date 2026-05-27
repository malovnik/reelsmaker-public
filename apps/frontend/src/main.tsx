import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

// Шрифты — самохост через @fontsource-variable. Inter Variable (UI body),
// Geist Variable (display numerals + hero), JetBrains Mono (service caps).
// CSS-переменные --font-sans/--font-display/--font-mono прописаны в globals.css.
import "@fontsource-variable/inter/index.css";
import "@fontsource-variable/geist/index.css";
import "@fontsource-variable/jetbrains-mono/index.css";

import "./globals.css";
import { router } from "./router";

const container = document.getElementById("root");
if (!container) {
  throw new Error("missing #root");
}

createRoot(container).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
