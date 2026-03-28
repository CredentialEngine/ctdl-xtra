import { z } from "zod";
import { merge } from "lodash";
import {
  defaultUserPreferences,
  EmailNotificationPreference,
  UserPreferences,
} from "../../../common/types";
import { publicProcedure, router } from ".";
import { AppError, AppErrors } from "../appErrors";
import {
  createUser,
  deleteUser,
  findAllUsers,
  findUserById,
  generateStrongPassword,
  patchUserPreferences as applyUserPreferencesPatch,
  resetUserPassword,
} from "../data/users";

export const usersRouter = router({
  detail: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .query(async (opts) => {
      const user = await findUserById(opts.input.id);
      if (!user) {
        return null;
      }
      return {
        ...user,
        userPreferences: merge(
          {},
          defaultUserPreferences(),
          user.userPreferences || {}
        ) as UserPreferences,
      };
    }),
  list: publicProcedure.query(async (_opts) => {
    return findAllUsers();
  }),
  create: publicProcedure
    .input(
      z.object({
        name: z.string().min(2),
        email: z.string().email().min(3).max(400),
      })
    )
    .mutation(async (opts) => {
      const { email, name } = opts.input;
      const generatedPassword = generateStrongPassword(12);
      const user = await createUser(email, generatedPassword, name);
      return {
        user,
        generatedPassword,
      };
    }),
  delete: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      const user = await findUserById(opts.input.id);
      if (!user) {
        throw new AppError("User not found", AppErrors.NOT_FOUND);
      }
      if (user.id == opts.ctx.user?.id) {
        throw new AppError(
          "User tried to delete themselves",
          AppErrors.BAD_REQUEST
        );
      }
      await deleteUser(user.id);
    }),
  resetPassword: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      const user = await findUserById(opts.input.id);
      if (!user) {
        throw new AppError("User not found", AppErrors.NOT_FOUND);
      }
      const generatedPassword = generateStrongPassword(12);
      await resetUserPassword(user.id, generatedPassword);
      return {
        user,
        generatedPassword,
      };
    }),
  redefinePassword: publicProcedure
    .input(
      z.object({
        password: z.string().min(6),
      })
    )
    .mutation(async (opts) => {
      await resetUserPassword(opts.ctx.user!.id, opts.input.password);
    }),
  patchUserPreferences: publicProcedure
    .input(
      z.object({
        email: z.object({
          notifications: z.nativeEnum(EmailNotificationPreference),
        }),
      })
    )
    .mutation(async (opts) => {
      const uid = opts.ctx.user?.id;
      if (!uid) {
        throw new AppError("Not authenticated", AppErrors.BAD_REQUEST);
      }
      const merged = await applyUserPreferencesPatch(uid, {
        email: opts.input.email,
      });
      if (!merged) {
        throw new AppError("User not found", AppErrors.NOT_FOUND);
      }
      return merged;
    }),
});
