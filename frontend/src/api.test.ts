import { describe, expect, it } from "vitest";
import { buildApiUrl, buildWsUrl } from "./api";

describe("buildApiUrl", () => {
  it("sem servidor configurado usa o mesmo endereço do site", () => {
    expect(buildApiUrl("", "/dashboard")).toBe("/api/dashboard");
  });
  it("com servidor online usa a URL configurada, sem barra dupla", () => {
    expect(buildApiUrl("https://fomo-ai.onrender.com/", "/dashboard")).toBe("https://fomo-ai.onrender.com/api/dashboard");
  });
});

describe("buildWsUrl", () => {
  it("local: mesmo host, ws://", () => {
    expect(buildWsUrl("", { protocol: "http:", host: "127.0.0.1:8765" }, null)).toBe("ws://127.0.0.1:8765/ws");
  });
  it("online: wss:// no servidor configurado, com o token", () => {
    expect(buildWsUrl("https://fomo-ai.onrender.com", { protocol: "https:", host: "x.github.io" }, "ab c"))
      .toBe("wss://fomo-ai.onrender.com/ws?token=ab%20c");
  });
});
