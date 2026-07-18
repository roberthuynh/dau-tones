import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// The interface is English with intentionally taught Vietnamese words. Prevent
// browser translation from turning “Dấu” into “Sign” or “Phương” into “Direction”.
document.documentElement.lang = "en";
document.documentElement.translate = false;
document.documentElement.setAttribute("translate", "no");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
