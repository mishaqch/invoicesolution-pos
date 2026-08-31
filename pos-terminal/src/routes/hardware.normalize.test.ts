import { describe, expect, it } from "vitest";

import { normalizeKitchenInterface } from "../lib/printer-interface";

describe("normalizeKitchenInterface", () => {
  it("turns a bare IPv4 into a tcp://IP:9100 network URI", () => {
    expect(normalizeKitchenInterface("192.168.1.20")).toBe("tcp://192.168.1.20:9100");
  });

  it("turns IP:port into tcp://IP:port", () => {
    expect(normalizeKitchenInterface("192.168.1.20:9100")).toBe("tcp://192.168.1.20:9100");
    expect(normalizeKitchenInterface("192.168.0.60:9101")).toBe("tcp://192.168.0.60:9101");
  });

  it("leaves an already-scheme'd tcp:// interface untouched", () => {
    expect(normalizeKitchenInterface("tcp://192.168.1.20:9100")).toBe("tcp://192.168.1.20:9100");
  });

  it("leaves a Windows printer name untouched (print layer adds win:)", () => {
    expect(normalizeKitchenInterface("POS-80-Series (1)")).toBe("POS-80-Series (1)");
    expect(normalizeKitchenInterface("win:POS-80")).toBe("win:POS-80");
  });

  it("leaves device paths / cups untouched", () => {
    expect(normalizeKitchenInterface("/dev/usb/lp0")).toBe("/dev/usb/lp0");
    expect(normalizeKitchenInterface("cups://Kitchen")).toBe("cups://Kitchen");
  });

  it("trims and treats blank as empty (clears the kitchen printer)", () => {
    expect(normalizeKitchenInterface("   ")).toBe("");
    expect(normalizeKitchenInterface("")).toBe("");
    expect(normalizeKitchenInterface("  192.168.1.20  ")).toBe("tcp://192.168.1.20:9100");
  });
});
