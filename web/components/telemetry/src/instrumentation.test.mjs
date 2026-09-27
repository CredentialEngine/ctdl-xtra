import { jest } from "@jest/globals";

const useAzureMonitor = jest.fn();
const resourceFromAttributes = jest.fn((attributes) => ({ attributes }));

jest.unstable_mockModule("server-only", () => ({}));
jest.unstable_mockModule("@azure/monitor-opentelemetry", () => ({
    useAzureMonitor,
}));
jest.unstable_mockModule("@opentelemetry/resources", () => ({
    resourceFromAttributes,
}));
jest.unstable_mockModule("@opentelemetry/semantic-conventions", () => ({
    ATTR_SERVICE_NAME: "service.name",
}));

const { register } = await import("../dist/instrumentation.js");
const originalEnv = { ...process.env };

afterEach(() => {
    process.env = { ...originalEnv };
    jest.clearAllMocks();
});

test("does nothing outside the Node.js Next runtime", async () => {
    process.env.NEXT_RUNTIME = "edge";
    await register();
    expect(useAzureMonitor).not.toHaveBeenCalled();
});

test("does nothing for local development", async () => {
    process.env.NEXT_RUNTIME = "nodejs";
    process.env.NEXT_PUBLIC_NODE_ENV = "development";
    await register();
    expect(useAzureMonitor).not.toHaveBeenCalled();
});

test("requires a connection string in deployed environments", async () => {
    process.env.NEXT_RUNTIME = "nodejs";
    process.env.NEXT_PUBLIC_NODE_ENV = "production";
    delete process.env.APPLICATIONINSIGHTS_CONNECTION_STRING;
    delete process.env.NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING;
    process.env.APPLICATION_INSIGHTS_CLOUD_ROLE_NAME = "finder";
    await expect(register()).rejects.toThrow(
        "APPLICATION_INSIGHTS_CONNECTION_STRING",
    );
});

test("requires a cloud role name in deployed environments", async () => {
    process.env.NEXT_RUNTIME = "nodejs";
    process.env.NEXT_PUBLIC_NODE_ENV = "production";
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING =
        "InstrumentationKey=test";
    delete process.env.APPLICATION_INSIGHTS_CLOUD_ROLE_NAME;
    delete process.env.NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME;
    await expect(register()).rejects.toThrow(
        "APPLICATION_INSIGHTS_CLOUD_ROLE_NAME",
    );
});

test("configures Azure Monitor with service identity", async () => {
    process.env.NEXT_RUNTIME = "nodejs";
    process.env.NEXT_PUBLIC_NODE_ENV = "production";
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING =
        "InstrumentationKey=test";
    process.env.APPLICATION_INSIGHTS_CLOUD_ROLE_NAME = "finder";
    await register();
    expect(resourceFromAttributes).toHaveBeenCalledWith({
        "service.name": "finder",
    });
    expect(useAzureMonitor).toHaveBeenCalledWith({
        azureMonitorExporterOptions: {
            connectionString: "InstrumentationKey=test",
        },
        resource: { attributes: { "service.name": "finder" } },
    });
});
