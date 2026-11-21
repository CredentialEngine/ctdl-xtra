import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { initTheme } from "./shell/theme";
import { startTelemetry } from "./telemetry";

initTheme();

const render = () => createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
// with telemetry on (telemetry/index.ts), wait for it, at most 1.5 s, so the first API calls are traced; off, at once
void Promise.race([startTelemetry(), new Promise((r) => setTimeout(r, 1500))]).then(render);
