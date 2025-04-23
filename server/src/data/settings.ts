import { eq } from "drizzle-orm";
import db from "../data";
import { decryptFromDb, encryptForDb, settings } from "../data/schema";

export async function findSettings() {
  return db.query.settings.findMany();
}

export async function findSettingJson<T>(key: string): Promise<T | null> {
  try {
    const setting = await db.query.settings.findFirst({
      where: eq(settings.key, key),
    });
    if (!setting) {
      return null;
    }
  
    let result: T | null = null;
    if (setting.isEncrypted) {
      result = JSON.parse(decryptFromDb(setting.value)) as T;
    } else {
      result = JSON.parse(setting.value) as T;
    }
  
    return result;
  } catch (e) {
    console.error(`Error getting setting ${key}`, e);
    return null;
  }
}

export async function createOrUpdate(
  key: string,
  value: string,
  isEncrypted: boolean = false,
  encryptedPreview: string | null
) {
  value = isEncrypted ? encryptForDb(value) : value;
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
