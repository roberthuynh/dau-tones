import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initBotId } from "botid/client/core";
import App from "./App";
import "./styles.css";

// The interface is English with intentionally taught Vietnamese words. Prevent
// browser translation from turning “Dấu” into “Sign” or “Phương” into “Direction”.
document.documentElement.lang = "en";
document.documentElement.translate = false;
document.documentElement.setAttribute("translate", "no");

initBotId({
  protect: [
    { path: "/api/coach", method: "POST", advancedOptions: { checkLevel: "basic" } },
    { path: "/api/drills/generate", method: "POST", advancedOptions: { checkLevel: "basic" } },
    { path: "/api/echo/transcribe", method: "POST", advancedOptions: { checkLevel: "basic" } },
    { path: "/api/echo/reveals/*", method: "POST", advancedOptions: { checkLevel: "basic" } },
  ],
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
