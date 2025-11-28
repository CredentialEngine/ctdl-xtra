import * as Airbrake from "@airbrake/node";
import cors from "@fastify/cors";
import fastifySecureSession from "@fastify/secure-session";
import fastifyStatic from "@fastify/static";
import {
  fastifyTRPCPlugin,
  FastifyTRPCPluginOptions,
} from "@trpc/server/adapters/fastify";
import argon2 from "argon2";
import "dotenv/config";
import fastify from "fastify";
import { z } from "zod";
import { appRouter, type AppRouter } from "./appRouter";
import { streamCsv } from "./csv";
import { findDataset } from "./data/datasets";
import { findUserByEmail } from "./data/users";
import { makeAirbrakePlugin } from "./fastifyAirbrakeNotifier";
import fastifySessionAuth, {
  requireAuthentication,
} from "./fastifySessionAuth";
import getLogger from "./logging";
import { createContext } from "./trpcContext";

const logger = getLogger("server");
const server = fastify();

let airbrake: Airbrake.Notifier | undefined;

if (process.env.AIRBRAKE_PROJECT_ID && process.env.AIRBRAKE_PROJECT_KEY) {
  airbrake = new Airbrake.Notifier({
    projectId: parseInt(process.env.AIRBRAKE_PROJECT_ID),
    projectKey: process.env.AIRBRAKE_PROJECT_KEY,
  });

  server.register(makeAirbrakePlugin(airbrake));
}

const CLIENT_PATH = process.env.CLIENT_PATH;

if (CLIENT_PATH) {
  server.register(fastifyStatic, {
    root: CLIENT_PATH,
  });
  const spaRoutes = [
    "/catalogues",
    "/extractions",
    "/data",
    "/users",
    "/profile",
    "/settings",
    "/logout",
  ];
  server.setNotFoundHandler((req, res) => {
    if (spaRoutes.some((prefix) => req.url.startsWith(prefix))) {
      res.status(200).sendFile("index.html", CLIENT_PATH);
    } else {
      res.status(404).send();
    }
  });
}

server.register(cors, {
  origin: [process.env.FRONTEND_URL!],
  credentials: true,
  exposedHeaders: ["Content-Disposition", "Content-Type"],
});

server.register(fastifySecureSession, {
  key: Buffer.from(process.env.COOKIE_KEY as string, "hex"),
  cookie: {
    path: "/",
  },
});

server.register(fastifySessionAuth);

server.register(async (instance) => {
  instance.addHook("preHandler", requireAuthentication);

  instance.register(fastifyTRPCPlugin, {
    prefix: "/trpc",
    trpcOptions: {
      router: appRouter,
      createContext,
      onError(opts) {
        logger.error(
          {
            path: opts.path,
            type: opts.error.name,
            message: opts.error.message,
          },
          "Error in tRPC request"
        );

        if (!airbrake) {
          return;
        }

        const url = `${opts.req.protocol}://${opts.req.headers.host}${opts.req.url}`;
        const notice: any = {
          error: opts.error,
          context: {
            userAddr: opts.req.ip,
            userAgent: opts.req.headers["user-agent"],
            url,
            httpMethod: opts.req.method,
            component: "fastify",
            route: opts.req.routeOptions.url,
          },
        };

        const referer = opts.req.headers.referer;
        if (referer) {
          notice.context.referer = referer;
        }

        airbrake.notify(notice);
      },
    } satisfies FastifyTRPCPluginOptions<AppRouter>["trpcOptions"],
  });

  instance.get("/me", async (req, rep) => {
    rep.send(req.user);
  });

  instance.post("/logout", async (req, rep) => {
    req.logOut();
  });

  instance.get(
    "/downloads/bulk_upload_template/:datasetId",
    async (request, reply) => {
      const { datasetId } = request.params as any;
      const dataset = await findDataset(datasetId);
      if (!dataset) {
        return reply.code(404).send({ error: "Dataset not found" });
      }
      const cataloguePiece = dataset.extraction.recipe.catalogue.name
        .replace(/[^a-zA-Z0-9]/g, "_")
        .replace(/_+/g, "_")
        .replace(/^_|_$/g, "")
        .substring(0, 50);
      const filename = `AICourseCrawl-BulkUploadTemplate-${datasetId}_${cataloguePiece}.csv`;

      return reply
        .headers({
          "Content-Type": "application/octet-stream",
          "Content-Disposition": `attachment; filename="${filename}"`,
        })
        .send(streamCsv(datasetId));
    }
  );
});

server.get("/up", async (request, reply) => {
  return reply.send();
});

server.get("/error", async (request, reply) => {
  throw new Error("oops");
});

export interface LoginParams {
  email: string;
  password: string;
}

const LoginSchema = z.object({
  email: z.string().email().min(3).max(400),
  password: z.string().min(6).max(400),
});

server.post("/login", async (req, rep) => {
  try {
    LoginSchema.parse(req.body);
  } catch (err) {
    return rep.code(400).send(err);
  }
  const { email, password } = req.body as z.infer<typeof LoginSchema>;

  const user = await findUserByEmail(email, true);
  if (!user) {
    return rep
      .code(422)
      .send({ error: "Could not authenticate with email and password" });
  }

  const passwordMatches = await argon2.verify(user.password, password);
  if (!passwordMatches) {
    return rep
      .code(422)
      .send({ error: "Could not authenticate with email and password" });
  }

  const userOmittedPassword = { ...user, password: undefined };
  req.logIn(userOmittedPassword);
  rep.send(userOmittedPassword);
});

const port = process.env.PORT || process.env.VITE_PORT;
server.listen(
  {
    port: port ? parseInt(port) : 3000,
    host: "0.0.0.0",
  },
  (err, address) => {
    if (err) {
      logger.error(err);
      process.exit(1);
    }
    logger.info(`Server is running on ${address}`);
  }
);
