import {
  defaultUserPreferences,
  EmailNotificationPreference,
} from "../../common/types";
import { merge } from "lodash";

export interface NotificationRecipientContext {
  triggeredByUserId: number | null;
}

export type NotificationUserRow = {
  id: number;
  email: string;
  userPreferences: unknown | null;
};

export function shouldSendNotificationEmail(
  row: NotificationUserRow,
  ctx: NotificationRecipientContext
): boolean {
  const preferences = merge({}, defaultUserPreferences(), row.userPreferences || {});
  const notificationPreference = preferences.email?.notifications ?? EmailNotificationPreference.ALWAYS;
  const isTriggeredByMe = row.id === ctx.triggeredByUserId;
  
  if (notificationPreference === EmailNotificationPreference.OFF) {
    return false;
  }
  if (notificationPreference === EmailNotificationPreference.ALWAYS) {
    return true;
  }
  if (
    notificationPreference === EmailNotificationPreference.MINE &&
    isTriggeredByMe
  ) {
    return true;
  }
  return false;
}
