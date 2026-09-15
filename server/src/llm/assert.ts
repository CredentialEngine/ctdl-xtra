export class BadToolCallResponseError extends Error {}

export class UnknownPaginationTypeError extends Error {}

export function assertBool(obj: Record<string, unknown>, key: string) {
  const value = obj[key];
  if (typeof value == "string") {
    if (["yes", "true"].includes(value.toLowerCase())) {
      return true;
    }
    if (["no", "false", "null"].includes(value.toLowerCase())) {
      return false;
    }
    throw new BadToolCallResponseError(
      `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
    );
  }
  if (typeof value == "boolean") {
    return value;
  }
  throw new BadToolCallResponseError(
    `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
  );
}

export function assertString(obj: Record<string, unknown>, key: string) {
  const value = obj[key];
  if (typeof value !== "string") {
    throw new BadToolCallResponseError(
      `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
    );
  }
  return value;
}

export function assertStringEnum<T extends string>(
  obj: Record<string, unknown>,
  key: string,
  values: readonly T[]
): T {
  const value = assertString(obj, key);
  if (!values.includes(value as T)) {
    throw new BadToolCallResponseError(
      `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
    );
  }
  return value as T;
}

export function assertNumber(
  obj: Record<string, unknown>,
  key: string
): number {
  const value = obj[key];
  if (typeof value === "string") {
    if (!value.match(/^\d+$/)) {
      throw new BadToolCallResponseError(
        `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
      );
    }
    return parseInt(value, 10);
  }
  if (typeof value !== "number") {
    throw new BadToolCallResponseError(
      `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
    );
  }
  return value;
}

export function assertArray<T>(obj: Record<string, unknown>, key: string): T[] {
  const value = obj[key];
  if (Array.isArray(value)) {
    return value as T[];
  }
  throw new BadToolCallResponseError(
    `Bad tool response value for ${key}. ${JSON.stringify(obj)}`
  );
}
