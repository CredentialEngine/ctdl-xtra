import { jest } from "@jest/globals";

const instances = [];
class MockApplicationInsights {
    constructor(options) {
        this.options = options;
        this.loadAppInsights = jest.fn();
        this.addTelemetryInitializer = jest.fn((fn) =>
            this.initializers.push(fn),
        );
        this.trackTrace = jest.fn();
        this.trackPageView = jest.fn();
        this.initializers = [];
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
    localStorage: {
        getItem: jest.fn(() => JSON.stringify({ alpha: true, beta: false })),
    },
};

const appInsights = await import("../dist/appInsights.js");

test("does not initialize without a connection string", () => {
    const previous = process.env.NEXT_PUBLIC_NODE_ENV;
    process.env.NEXT_PUBLIC_NODE_ENV = "development";
    const warn = jest
        .spyOn(console, "warn")
        .mockImplementation(() => undefined);
    expect(appInsights.initializeAppInsights("", "finder")).toBeUndefined();
    expect(warn).toHaveBeenCalled();
    process.env.NEXT_PUBLIC_NODE_ENV = previous;
});

test("initializes Application Insights once per active connection string", () => {
    const instance = appInsights.initializeAppInsights(
        "InstrumentationKey=one",
        "finder",
    );
    expect(instance).toBe(instances[0]);
    expect(instance.loadAppInsights).toHaveBeenCalledTimes(1);
    expect(instance.addTelemetryInitializer).toHaveBeenCalledTimes(2);
    expect(appInsights.getReactPlugin()).toBeInstanceOf(MockReactPlugin);
    expect(appInsights.getClickPlugin()).toBeInstanceOf(MockClickPlugin);
    expect(
        appInsights.initializeAppInsights("InstrumentationKey=one", "finder"),
    ).toBe(instance);
    expect(instances).toHaveLength(1);
});

test("telemetry initializers set cloud role and experiment properties", () => {
    const instance = appInsights.getAppInsights();
    const envelope = { baseData: {} };
    for (const initializer of instance.initializers) initializer(envelope);
    expect(envelope.tags["ai.cloud.role"]).toBe("finder");
    expect(envelope.tags["ai.cloud.roleInstance"]).toBe("finder");
    expect(envelope.baseData.properties.ExperimentsConfig).toBe('["alpha"]');
});

test("trackClientTrace maps severity and sanitizes properties and measurements", () => {
    const instance = appInsights.getAppInsights();
    instance.trackTrace.mockClear();
    appInsights.trackClientTrace({
        message: "problem",
        severity: "error",
        properties: {
            error: new Error("boom"),
            enabled: true,
            object: { a: 1 },
            empty: undefined,
        },
        measurements: { duration: 12.5, invalid: Number.NaN },
    });
    expect(instance.trackTrace).toHaveBeenCalledWith(
        { message: "problem", severityLevel: 3 },
        expect.objectContaining({
            error: "Error: boom",
            enabled: "true",
            object: '{"a":1}',
            duration: 12.5,
        }),
    );
    expect(instance.trackTrace.mock.calls[0][1]).not.toHaveProperty("empty");
    expect(instance.trackTrace.mock.calls[0][1]).not.toHaveProperty("invalid");
});

test("clientLogger delegates all supported severity levels", () => {
    const instance = appInsights.getAppInsights();
    instance.trackTrace.mockClear();
    appInsights.clientLogger.verbose("v");
    appInsights.clientLogger.info("i");
    appInsights.clientLogger.warn("w");
    appInsights.clientLogger.error("e");
    appInsights.clientLogger.critical("c");
    expect(
        instance.trackTrace.mock.calls.map(([trace]) => trace.severityLevel),
    ).toEqual([0, 1, 2, 3, 4]);
});
