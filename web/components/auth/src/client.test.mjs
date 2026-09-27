import { jest } from "@jest/globals";

const fakeContext = { Provider: Symbol("Provider") };
let contextValue = null;
const signInMock = jest.fn();

jest.unstable_mockModule("react", () => ({
    createContext: () => fakeContext,
    useCallback: (fn) => fn,
    useContext: () => contextValue,
    useEffect: () => undefined,
    useMemo: (fn) => fn(),
    useRef: (value) => ({ current: value }),
    useState: (value) => [value, jest.fn()],
}));

jest.unstable_mockModule("react/jsx-runtime", () => ({
    jsx: (type, props) => ({ type, props }),
    jsxs: (type, props) => ({ type, props }),
    Fragment: Symbol("Fragment"),
}));

jest.unstable_mockModule("next-auth/react", () => ({
    signIn: signInMock,
}));

const client = await import("../dist/client.js");

function installWindow(path = "/search?query=quality#results") {
    const assign = jest.fn();
    const replace = jest.fn();

    globalThis.window = {
        location: {
            pathname: path.split(/[?#]/)[0],
            search: path.includes("?")
                ? `?${path.split("?")[1].split("#")[0]}`
                : "",
            hash: path.includes("#") ? `#${path.split("#")[1]}` : "",
            assign,
            replace,
        },
    };

    return { assign, replace };
}

beforeEach(() => {
    jest.clearAllMocks();
});

test("redirectToBffHome replaces immediately for a normal logout", () => {
    const { replace } = installWindow("/profile");

    client.redirectToBffHome(false);

    expect(replace).toHaveBeenCalledWith("/");
});

test("useBffAuth rejects usage outside its provider", () => {
    contextValue = null;

    expect(() => client.useBffAuth()).toThrow(
        "useBffAuth must be used within BffAuthProvider",
    );
});

test("BffAuthProvider renders its fallback during initial auth loading", () => {
    installWindow("/");

    const result = client.BffAuthProvider({
        children: "app",
        fallback: "loading",
    });

    expect(result.type).toBe(fakeContext.Provider);
    expect(result.props.children).toBe("loading");
});

test("login calls signIn with keycloak and current callback url", () => {
    installWindow("/dashboard?tab=overview#section");

    const result = client.BffAuthProvider({
        children: "app",
    });

    const value = result.props.value;

    value.login();

    expect(signInMock).toHaveBeenCalledWith(
        "keycloak",
        {
            callbackUrl: "/dashboard?tab=overview#section",
        },
        undefined,
    );
});

test("login passes authorization parameters to signIn", () => {
    installWindow("/");

    const result = client.BffAuthProvider({
        children: "app",
    });

    const value = result.props.value;

    value.login("/", {
        prompt: "none",
    });

    expect(signInMock).toHaveBeenCalledWith(
        "keycloak",
        {
            callbackUrl: "/",
        },
        {
            prompt: "none",
        },
    );
});

test("hasRole returns false when no user is present", () => {
    installWindow("/");

    const result = client.BffAuthProvider({
        children: "app",
    });

    const value = result.props.value;

    expect(value.hasRole("admin")).toBe(false);
});
