import { describe, expect, it } from "vitest";
import { formatAge, formatPct, formatPrice, formatUsd } from "./format";

describe("formatUsd", () => {
  it("usa duas casas e separador brasileiro", () => {
    expect(formatUsd(1234.5)).toBe("US$ 1.234,50");
    expect(formatUsd(-2.5)).toBe("−US$ 2,50");
  });
  it("mostra traço para ausente", () => {
    expect(formatUsd(null)).toBe("—");
    expect(formatUsd(undefined)).toBe("—");
  });
});

describe("formatPrice", () => {
  it("preços muito pequenos mantêm 4 dígitos significativos", () => {
    expect(formatPrice(0.00001187308)).toBe("US$ 0,00001187");
  });
  it("preços normais com 4 casas", () => {
    expect(formatPrice(1.23456)).toBe("US$ 1,2346");
  });
  it("ausente", () => {
    expect(formatPrice(null)).toBe("—");
  });
});

describe("formatPct", () => {
  it("sinal explícito", () => {
    expect(formatPct(2.345)).toBe("+2,35%");
    expect(formatPct(-1)).toBe("−1,00%");
  });
});

describe("formatAge", () => {
  const now = new Date("2026-10-31T12:00:00Z").getTime();
  it("segundos, minutos, horas e dias", () => {
    expect(formatAge("2026-10-31T11:59:30Z", now)).toBe("30 s");
    expect(formatAge("2026-10-31T11:15:00Z", now)).toBe("45 min");
    expect(formatAge("2026-10-31T07:00:00Z", now)).toBe("5 h");
    expect(formatAge("2026-10-28T12:00:00Z", now)).toBe("3 d");
  });
  it("ausente", () => {
    expect(formatAge(null, now)).toBe("—");
  });
});

describe("formatIn", () => {
  const now = new Date("2026-10-31T12:00:00Z").getTime();
  it("tempo restante", async () => {
    const { formatIn } = await import("./format");
    expect(formatIn("2026-10-31T12:07:00Z", now)).toBe("7 min");
    expect(formatIn("2026-10-31T11:59:00Z", now)).toBe("agora");
  });
});
