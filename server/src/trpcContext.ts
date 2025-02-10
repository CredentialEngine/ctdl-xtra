import { CreateFastifyContextOptions } from "@trpc/server/adapters/fastify";
export function createContext({ req, res }: CreateFastifyContextOptions) {
  const user = req.user;
  const orgId = req.headers['x-ce-org-id'];
  return { req, res, user, orgId };
}
export type Context = Awaited<ReturnType<typeof createContext>>;
