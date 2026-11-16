import { describe, expect, it } from "vitest";
import {
  attachWorkerCatchContext,
  buildWorkerAirbrakeNotice,
  extractionFieldsFromJobData,
  redactProxyUrlForAirbrake,
  workerAirbrakeInputForJobFailure,
} from "../src/workerAirbrakeNotice";

describe("workerAirbrakeNotice", () => {
  it("reads job payload fields", () => {
    expect(
      extractionFieldsFromJobData({
        crawlPageId: 1,
        extractionId: 42,
        datasetId: 3,
      })
    ).toEqual({
      crawlPageId: 1,
      extractionId: 42,
      datasetId: 3,
    });
  });

  it("builds a notice with error, context, and params", () => {
    const cause = new Error("fetch timed out");
    attachWorkerCatchContext(cause, {
      extractionId: 10,
      crawlPageId: 20,
      datasetId: 30,
      url: "https://example.edu/page",
      responseStatus: 503,
    });

    const notice = buildWorkerAirbrakeNotice(
      workerAirbrakeInputForJobFailure(
        cause,
        { extractionId: 10, crawlPageId: 20, datasetId: 30 },
        "extractions.fetchPage.default"
      )
    );

    expect(notice.error).toBe(cause);
    expect(notice.params).toEqual({
      extractionId: 10,
      crawlPageId: 20,
      datasetId: 30,
      url: "https://example.edu/page",
      responseStatus: 503,
    });
    expect(notice.context).toEqual({
      component: "worker",
      jobName: "extractions.fetchPage.default",
    });
  });

  it("redacts proxy credentials for airbrake", () => {
    expect(
      redactProxyUrlForAirbrake("http://user:secret@proxy.example:8080")
    ).toBe("http://user:redacted@proxy.example:8080/");
  });

  it("includes proxyUsed on the airbrake notice", () => {
    const err = new Error("timeout");
    attachWorkerCatchContext(err, {
      extractionId: 1,
      proxyUrl: "http://user:secret@proxy.example:8080",
    });

    const notice = buildWorkerAirbrakeNotice(
      workerAirbrakeInputForJobFailure(err, { extractionId: 1 })
    );

    expect(notice.params?.proxyUsed).toBe(
      "http://user:redacted@proxy.example:8080/"
    );
  });

  it("records direct connection on the airbrake notice", () => {
    const err = new Error("timeout");
    attachWorkerCatchContext(err, { extractionId: 1, directConnection: true });

    const notice = buildWorkerAirbrakeNotice(
      workerAirbrakeInputForJobFailure(err, { extractionId: 1 })
    );

    expect(notice.params?.proxyUsed).toBe("direct");
  });

  it("merges attached catch context over job data", () => {
    const err = new Error("boom");
    attachWorkerCatchContext(err, { url: "https://from-worker.example" });

    const input = workerAirbrakeInputForJobFailure(
      err,
      { extractionId: 1, crawlPageId: 2, datasetId: 3 },
      "extractions.extractData.default"
    );

    expect(input.url).toBe("https://from-worker.example");
    expect(input.extractionId).toBe(1);
    expect(input.jobName).toBe("extractions.extractData.default");
  });
});