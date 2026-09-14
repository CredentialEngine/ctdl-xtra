import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  LOGIN_PATH,
  loginPathWithReturnTo,
  REDIRECT_PARAM,
  safeReturnTo,
  safeReturnToFromSearch,
} from "./loginRedirect.ts";

describe("loginPathWithReturnTo", () => {
  it("returns the login path when there is no destination", () => {
    assert.equal(loginPathWithReturnTo(""), LOGIN_PATH);
  });

  it("returns the login path when the destination is already login", () => {
    assert.equal(loginPathWithReturnTo(LOGIN_PATH), LOGIN_PATH);
  });

  it("appends an encoded redirect query for in-app paths", () => {
    assert.equal(
      loginPathWithReturnTo("/catalogues/91"),
      `${LOGIN_PATH}?${REDIRECT_PARAM}=%2Fcatalogues%2F91`
    );
  });

  it("preserves destination query strings in the redirect param", () => {
    assert.equal(
      loginPathWithReturnTo("/extractions?page=2"),
      `${LOGIN_PATH}?${REDIRECT_PARAM}=%2Fextractions%3Fpage%3D2`
    );
  });
});

describe("safeReturnTo", () => {
  it("rejects empty values", () => {
    assert.equal(safeReturnTo(null), undefined);
    assert.equal(safeReturnTo(""), undefined);
  });

  it("accepts same-origin app paths", () => {
    assert.equal(safeReturnTo("/catalogues/91"), "/catalogues/91");
  });

  it("accepts same-origin paths that include a query string", () => {
    assert.equal(safeReturnTo("/extractions?page=2"), "/extractions?page=2");
  });

  it("rejects the login path", () => {
    assert.equal(safeReturnTo("/"), undefined);
    assert.equal(safeReturnTo("/?redirect=/catalogues/91"), undefined);
  });

  it("rejects the logout path", () => {
    assert.equal(safeReturnTo("/logout"), undefined);
    assert.equal(safeReturnTo("/logout?next=/"), undefined);
  });

  it("keeps only the path and query from absolute or protocol-relative URLs", () => {
    assert.equal(safeReturnTo("https://evil.example/catalogues/91"), "/catalogues/91");
    assert.equal(
      safeReturnTo("https://evil.example/extractions?page=2"),
      "/extractions?page=2"
    );
    assert.equal(safeReturnTo("//evil.example/catalogues/91"), "/catalogues/91");
    assert.equal(safeReturnTo("https://evil.example"), undefined);
    assert.equal(safeReturnTo("//evil.example"), undefined);
  });

  it("resolves relative paths against the app origin", () => {
    assert.equal(safeReturnTo("catalogues/91"), "/catalogues/91");
  });

  it("rejects values that do not yield a root-relative path", () => {
    assert.equal(safeReturnTo("javascript:alert(1)"), undefined);
  });
});

describe("safeReturnToFromSearch", () => {
  it("returns undefined when the redirect param is missing", () => {
    assert.equal(safeReturnToFromSearch(""), undefined);
    assert.equal(safeReturnToFromSearch("foo=bar"), undefined);
  });

  it("decodes a safe redirect param", () => {
    assert.equal(
      safeReturnToFromSearch("redirect=%2Fcatalogues%2F91"),
      "/catalogues/91"
    );
    assert.equal(
      safeReturnToFromSearch("redirect=%2Fextractions%3Fpage%3D2"),
      "/extractions?page=2"
    );
  });

  it("rejects unsafe redirect params after decoding", () => {
    assert.equal(
      safeReturnToFromSearch("redirect=%2F%2Fevil.example"),
      undefined
    );
    assert.equal(safeReturnToFromSearch("redirect=%2Flogout"), undefined);
    assert.equal(safeReturnToFromSearch("redirect=%2F"), undefined);
  });
});
