import { describe, expect, it } from "vitest";
import { doorLabel, livePlatform, platformLabel } from "./platform";

describe("platformLabel", () => {
  it("names a single certain platform", () => {
    expect(platformLabel({ numbers: ["3"], door: "left", certain: true })).toBe("PF 3");
  });
  it("compresses consecutive platforms and says usually when uncertain", () => {
    expect(platformLabel({ numbers: ["5", "6", "7"], door: null, certain: false })).toBe("Usually PF 5–7");
  });
  it("lists platforms that don't run on", () => {
    expect(platformLabel({ numbers: ["1", "1A", "4"], door: null, certain: false })).toBe("Usually PF 1, 1A, 4");
  });
  it("keeps two consecutive platforms listed", () => {
    expect(platformLabel({ numbers: ["5", "6"], door: null, certain: false })).toBe("Usually PF 5, 6");
  });
});

describe("doorLabel", () => {
  it("says which side the doors open", () => {
    expect(doorLabel("left")).toBe("Doors left");
    expect(doorLabel("right")).toBe("Doors right");
    expect(doorLabel("both")).toBe("Doors both sides");
    expect(doorLabel(null)).toBeNull();
  });
});

describe("livePlatform", () => {
  it("rebuilds a platform from the live table's columns", () => {
    expect(livePlatform("5,6", false, "right")).toEqual({ numbers: ["5", "6"], door: "right", certain: false });
    expect(livePlatform(null, false, null)).toBeNull();
    expect(livePlatform("", true, "left")).toBeNull();
  });
});
