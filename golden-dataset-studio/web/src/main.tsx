import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { initTheme } from "./shell/theme";
import { startTelemetry } from "./telemetry";

initTheme();
void startTelemetry(); // off unless the server configures it (telemetry/index.ts)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
