import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { KcPage } from "./kc.gen";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>{window.kcContext ? <KcPage kcContext={window.kcContext} /> : <h1>No Keycloak context</h1>}</StrictMode>,
  );
}
