import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, HashRouter } from "react-router-dom";
import App from "./App";
import AuthGate from "./components/AuthGate";
import "./index.css";

// O GitHub Pages não redireciona /portfolio para o index.html; lá as rotas ficam em #/portfolio
const Router = import.meta.env.VITE_ROUTER === "hash" ? HashRouter : BrowserRouter;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Router>
      <AuthGate>
        <App />
      </AuthGate>
    </Router>
  </React.StrictMode>,
);
