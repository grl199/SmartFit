import {clampPercent,formatKcal,localDateISO} from "../src/lib/format";
describe("format helpers",()=>{
  it("clamps progress between zero and one hundred",()=>{
    expect(clampPercent(50,100)).toBe(50);
    expect(clampPercent(150,100)).toBe(100);
    expect(clampPercent(-1,100)).toBe(0);
  });
  it("returns zero progress for invalid targets",()=>{
    expect(clampPercent(25,0)).toBe(0);
    expect(clampPercent(Number.NaN,100)).toBe(0);
  });
  it("formats calories with Spanish locale",()=>{
    expect(formatKcal(1234)).toBe("1.234");
    expect(formatKcal(undefined)).toBe("0");
  });
  it("formats a local calendar date without timezone shifts",()=>{
    expect(localDateISO(new Date(2026,0,9,12))).toBe("2026-01-09");
  });
});