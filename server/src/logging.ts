import pino from "pino";

const { LOG_LEVEL = "debug" } = process.env;
const isProduction = process.env.NODE_ENV === "production";

const logger = pino({
  name: "ctdl-xtra-web",
  level: LOG_LEVEL,
  ...(!isProduction && {
    transport: {
      target: "pino-pretty",
      options: {
        colorize: true,
        levelFirst: true,
        translateTime: true,
      },
    },
  }),
});

export default function getLogger(category = "") {
  if (!category) {
    return logger;
  }

  return logger.child({
    category,
  });
}
