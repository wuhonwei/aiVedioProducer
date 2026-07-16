import { describe, expect, it } from "vitest";
import { defaultProbePrompt } from "../pages/VisualPage";

describe("defaultProbePrompt", () => {
  it("uses prompt_zh when present", () => {
    const p = defaultProbePrompt({
      name: "林砚之",
      prompt_zh: "林砚之，行旅青年，身着青灰布衣与半旧蓝布包袱",
    });
    expect(p).toContain("蓝布包袱");
    expect(p).toContain("1person");
    expect(p).toContain("人物半身特写");
  });

  it("falls back to name", () => {
    const p = defaultProbePrompt({ name: "周大人", prompt_zh: "" });
    expect(p.startsWith("周大人")).toBe(true);
    expect(p).toContain("upper body portrait");
  });

  it("differs across characters", () => {
    const a = defaultProbePrompt({
      name: "苏婆婆",
      prompt_zh: "苏婆婆，白发花白发髻，粗布家常衣衫",
    });
    const b = defaultProbePrompt({
      name: "周大人",
      prompt_zh: "周大人，中年吏员，深色官服长袍",
    });
    expect(a).not.toBe(b);
  });
});
