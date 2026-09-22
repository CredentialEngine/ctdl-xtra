import { jest } from "@jest/globals";
jest.unstable_mockModule("server-only", () => ({}));
const api = await import("../dist/index.js");
test("package index exports register", () => {
    expect(typeof api.register).toBe("function");
});
