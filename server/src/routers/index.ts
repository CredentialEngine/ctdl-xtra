import { initTRPC, TRPCError } from "@trpc/server";
import { AppError, AppErrors } from "../appErrors";
import { Context } from "../trpcContext";

const t = initTRPC.context<Context>().create();

function trpcCodeForAppError(error: AppError): TRPCError["code"] {
  return error.code === AppErrors.NOT_FOUND ? "NOT_FOUND" : "BAD_REQUEST";
}

const mapAppError = t.middleware(async ({ next }) => {
  try {
    const result = await next();
    if (!result.ok && result.error.cause instanceof AppError) {
      throw new TRPCError({
        code: trpcCodeForAppError(result.error.cause),
        message: result.error.cause.message,
      });
    }
    return result;
  } catch (err) {
    if (err instanceof AppError) {
      throw new TRPCError({
        code: trpcCodeForAppError(err),
        message: err.message,
      });
    }
    throw err;
  }
});

export const router = t.router;
export const publicProcedure = t.procedure.use(mapAppError);
