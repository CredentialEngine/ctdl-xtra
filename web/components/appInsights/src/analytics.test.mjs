import { jest } from "@jest/globals";

const instances = [];
class MockApplicationInsights {
    constructor() {
        this.loadAppInsights = jest.fn();
        this.addTelemetryInitializer = jest.fn();
        this.trackTrace = jest.fn();
        this.trackPageView = jest.fn();
        instances.push(this);
    }
}
class MockReactPlugin {
    constructor() {
        this.identifier = "reactPlugin";
    }
}
class MockClickPlugin {
    constructor() {
        this.identifier = "clickPlugin";
    }
}

jest.unstable_mockModule("react", () => ({ useEffect: (fn) => fn() }));
jest.unstable_mockModule("next/navigation", () => ({
    usePathname: () => "/search",
    useSearchParams: () => ({ toString: () => "query=quality&page=2" }),
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

globalThis.window = {
    location: { href: "https://finder.example/search?query=quality&page=2" },
    localStorage: { getItem: () => null },
};
const { Analytics } = await import("../dist/analytics.js");

test("tracks the current App Router page after initialization", () => {
    expect(
        Analytics({ connectionString: "connection", roleName: "finder" }),
    ).toBeNull();
    expect(instances).toHaveLength(1);
    expect(instances[0].trackPageView).toHaveBeenCalledWith({
        name: "/search",
        uri: "https://finder.example/search?query=quality&page=2",
        properties: {
            path: "/search",
            queryString: "query=quality&page=2",
            source: "next-app-router",
        },
    });
});

test("does nothing when required configuration is missing", () => {
    const count = instances.length;
    Analytics({ connectionString: "", roleName: "finder" });
    expect(instances).toHaveLength(count);
});
