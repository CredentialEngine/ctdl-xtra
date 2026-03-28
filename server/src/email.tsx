import { renderAsync } from "@react-email/components";
import { asc } from "drizzle-orm";
import nodemailer from "nodemailer";
import QueryStream from "pg-query-stream";
import db, { pool } from "./data";
import { users } from "./data/schema";
import { Email } from "./emails";
import getLogger from "./logging";
import {
  NotificationRecipientContext,
  NotificationUserRow,
  shouldSendNotificationEmail,
} from "./notifications";

const logger = getLogger("email");

const NOTIFICATION_BATCH_SIZE = 50;

let transporter: nodemailer.Transporter;

async function getMailer() {
  if (transporter) {
    return transporter;
  }
  if (!process.env.SMTP_USER || !process.env.SMTP_PASSWORD) {
    const testAccount = await nodemailer.createTestAccount();
    transporter = nodemailer.createTransport({
      host: testAccount.smtp.host,
      port: testAccount.smtp.port,
      secure: testAccount.smtp.secure,
      auth: {
        user: testAccount.user,
        pass: testAccount.pass,
      },
    });
    return transporter;
  }
  transporter = nodemailer.createTransport({
    host: "email-smtp.us-east-1.amazonaws.com",
    port: 465,
    secure: true,
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASSWORD,
    },
  });
  return transporter;
}

async function sendMail(to: string[], subject: string, html: string) {
  const mailer = await getMailer();
  const params = {
    from: "CTDL xTRA <do-not-reply.ctdl-xtra@credentialengineregistry.org>",
    to,
    subject,
    html,
  };
  return await mailer.sendMail(params);
}

function normalizeUserStreamRow(
  raw: Record<string, unknown>
): NotificationUserRow {
  return {
    id: raw.id as number,
    email: raw.email as string,
    userPreferences:
      (raw.userPreferences ?? raw.user_preferences) as unknown | null,
  };
}

export async function sendEmailToAll<T>(
  EmailComponent: Email<T>,
  props: T & {},
  subject?: string,
  notificationCtx?: NotificationRecipientContext
) {
  const emailHtml = await renderAsync(<EmailComponent {...props} />);
  const ctx: NotificationRecipientContext = notificationCtx ?? {
    triggeredByUserId: null,
  };
  subject = subject || EmailComponent.DefaultSubject || "";

  const query = db
    .select({
      id: users.id,
      email: users.email,
      userPreferences: users.userPreferences,
    })
    .from(users);

  const { sql: rawSql, params } = query.toSQL();

  const client = await pool.connect();
  try {
    const queryStream = new QueryStream(rawSql, params, { batchSize: NOTIFICATION_BATCH_SIZE });
    const stream = client.query(queryStream);

    const emailPromises: Promise<void>[] = [];

    for await (const raw of stream as AsyncIterable<Record<string, unknown>>) {
      const user = normalizeUserStreamRow(raw);
      const email = user.email;
      if (shouldSendNotificationEmail(user, ctx)) {
        sendMail([email], subject, emailHtml).catch((err) => {
          logger.error({ err }, "Notification email send failed");
        });
      }
    }
  } finally {
    client.release();
  }
}
