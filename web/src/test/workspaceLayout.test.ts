import { describe, expect, it } from "vitest";
import { num, pct, regionLabel } from "../components/workspace/Layout";

describe("workspace formatting helpers", () => {
  it("labels regions from their keys without hard-coding basin names", () => {
    expect(regionLabel("nio")).toBe("North Indian Ocean domain");
    expect(regionLabel("bay_of_bengal")).toBe("Bay of Bengal");
    expect(regionLabel("arabian_sea")).toBe("Arabian Sea");
  });

  it("never turns a missing value into a number", () => {
    expect(pct(null)).toBe("—");
    expect(pct(Number.NaN)).toBe("—");
    expect(num(undefined)).toBe("—");
    expect(num(Number.POSITIVE_INFINITY, 1, "°C")).toBe("—");
  });

  it("formats present values with their unit", () => {
    expect(pct(0.1234, 1)).toBe("12.3 %");
    expect(num(22.34, 2, "°C")).toBe("22.34 °C");
    expect(num(0, 1)).toBe("0.0");
  });
});
