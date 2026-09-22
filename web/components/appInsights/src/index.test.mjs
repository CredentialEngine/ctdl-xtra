import { jest } from "@jest/globals";
class MockApplicationInsights {}
class MockReactPlugin {
    constructor() {
        this.identifier = "react";
    }
}
class MockClickPlugin {
    constructor() {
        this.identifier = "click";
    }
}
jest.unstable_mockModule("next/navigation", () => ({
    usePathname: () => "/",
    useSearchParams: () => ({ toString: () => "" }),
}));
jest.unstable_mockModule("@microsoft/applicationinsights-web", () => ({
    ApplicationInsights: MockApplicationInsights,
}));
jest.unstable_mockModule("@microsoft/applicationinsights-react-js", () => ({
    ReactPlugin: MockReactPlugin,
}));
jest.unstable_mockModule(
    "@microsoft/applicationinsights-clickanalytics-js",
    () => ({
        ClickAnalyticsPlugin: MockClickPlugin,
    }),
);
const api = await import("../dist/index.js");
test("package index exports its public API", () => {
    expect(typeof api.Analytics).toBe("function");
    expect(typeof api.initializeAppInsights).toBe("function");
});
