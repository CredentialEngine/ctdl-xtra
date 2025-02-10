import { FastifyPluginCallback, FastifyReply, FastifyRequest } from "fastify";
import fastifyPlugin from "fastify-plugin";
import { findUserById } from "./data/users";
import { User } from "./types";

const fastifySessionAuth: FastifyPluginCallback = fastifyPlugin(
  function (fastify, opts, done) {
    fastify.decorateRequest("user", null);
    fastify.decorateRequest("isAuthenticated", function () {
      return !!this.user;
    });
    fastify.decorateRequest("logIn", function (user: User) {
      this.user = user;
      this.session.set("userId", user.id.toString());
    });
    fastify.decorateRequest("logOut", function () {
      this.user = undefined;
      this.session.set("userId", undefined);
    });
    fastify.addHook("onRequest", async (req, res) => {
      if (req.isAuthenticated()) {
        return;
      }

      const userId = req.session.get("userId");
      if (userId) {
        const user = await findUserById(parseInt(userId));
        if (user) {
          req.user = user;
          // add selected orgId to the user context
        } else {
          req.session.set("userId", undefined);
        }
      }
    });
    done();
  }
);

const requireAuthentication = async (
  req: FastifyRequest,
  rep: FastifyReply
) => {
  if (!req.isAuthenticated()) {
    await rep.code(401).send({ error: "Not Authorized" });
  }
};

export { requireAuthentication };

export default fastifySessionAuth;
