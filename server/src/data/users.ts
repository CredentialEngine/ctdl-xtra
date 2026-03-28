import { hash } from "argon2";
import { eq } from "drizzle-orm";
import { merge } from "lodash";
import {
  defaultUserPreferences,
  UserPreferences,
} from "../../../common/types";
import db from "../data";
import { users } from "./schema";

export function generateStrongPassword(length: number): string {
  const chars =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()_+[]{}|;:,.<>?";
  let password = "";
  for (let i = 0; i < length; i++) {
    const randomIndex = Math.floor(Math.random() * chars.length);
    password += chars[randomIndex];
  }
  return password;
}

export async function findUserById(
  id: number,
  includePassword: boolean = false
) {
  const columns = includePassword
    ? undefined
    : {
        password: false,
      };
  return db.query.users.findFirst({
    columns,
    where: (users, { eq }) => eq(users.id, id),
  });
}

export async function findUserByEmail(
  email: string,
  includePassword: boolean = false
) {
  const columns = includePassword
    ? undefined
    : {
        password: false,
      };
  return db.query.users.findFirst({
    columns,
    where: (users, { eq }) => eq(users.email, email),
  });
}

export async function findAllUsers() {
  return db.query.users.findMany({
    columns: {
      password: false,
      userPreferences: false,
    },
    orderBy: (u) => u.createdAt,
  });
}

export async function getAllEmailAddresses() {
  const emails = await db.query.users.findMany({
    columns: {
      email: true,
    },
    orderBy: (u) => u.createdAt,
  });
  return emails.map((e) => e.email);
}

export async function createUser(
  email: string,
  password: string,
  name: string
) {
  const encryptedPassword = await hash(password);
  const result = await db
    .insert(users)
    .values({ email, password: encryptedPassword, name })
    .returning();
  return { ...result[0], password: undefined };
}

export async function deleteUser(id: number) {
  return db.delete(users).where(eq(users.id, id));
}

export async function resetUserPassword(id: number, password: string) {
  const encryptedPassword = await hash(password);
  const result = await db
    .update(users)
    .set({ password: encryptedPassword })
    .where(eq(users.id, id))
    .returning();
  return { ...result[0], password: undefined };
}

export type UserPreferencesPatch = Partial<
  Pick<UserPreferences, "email">
> & {
  email?: Partial<NonNullable<UserPreferences["email"]>>;
};

export async function patchUserPreferences(
  userId: number,
  patch: UserPreferencesPatch
) {
  const row = await db.query.users.findFirst({
    columns: { userPreferences: true },
    where: (users, { eq }) => eq(users.id, userId),
  });
  if (!row) {
    return null;
  }
  const current: UserPreferences = merge(
    {},
    defaultUserPreferences(),
    row.userPreferences ?? {}
  );
  const next: UserPreferences = merge({}, current, patch);
  await db
    .update(users)
    .set({ userPreferences: next })
    .where(eq(users.id, userId));
  
  return next;
}
