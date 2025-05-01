import { eq } from "drizzle-orm";
import db from "../data";
import { decryptFromDb, encryptForDb, settings } from "../data/schema";

export async function findSetting<T>(key: string, decrypt: boolean = false) {
  const setting = await db.query.settings.findFirst({
    where: eq(settings.key, key),
  });
  if (!setting) {
    return null;
  }
  let value: any = setting.value;
  if (setting.isEncrypted) {
    if (decrypt) {
      value = JSON.parse(decryptFromDb(setting.value));
    } else {
      value = "[redacted]";
    }
  } else {
    value = JSON.parse(value) as T;
  }
  return { ...setting, value };
}

export async function createOrUpdate(options: {
  key: string;
  value: any;
  isEncrypted?: boolean;
  encryptedPreview?: string | null;
}) {
  let { key, value, isEncrypted = false, encryptedPreview = null } = options;
  value = JSON.stringify(value);
  if (isEncrypted) {
    value = encryptForDb(value);
  }
  return db
    .insert(settings)
    .values({
      key,
      value,
      isEncrypted,
      encryptedPreview,
    })
    .onConflictDoUpdate({
      target: settings.key,
      set: { value, isEncrypted, encryptedPreview },
    });
}
