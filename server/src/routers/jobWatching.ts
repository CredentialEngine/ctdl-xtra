import { z } from "zod";
import { publicProcedure, router } from ".";
import { getJobWatchLogs, getJobWatchStatus } from "../jobWatching";

export const jobWatchingRouter = router({
  status: publicProcedure
    .input(
      z.object({
        watchKey: z.string().min(1),
      })
    )
    .query(async (opts) => {
      return getJobWatchStatus(opts.input.watchKey);
    }),
  logs: publicProcedure
    .input(
      z.object({
        watchKey: z.string().min(1),
        startLineIndex: z.number().int().min(0).optional(),
      })
    )
    .query(async (opts) => {
      return getJobWatchLogs(
        opts.input.watchKey,
        opts.input.startLineIndex ?? 0
      );
    }),
});
