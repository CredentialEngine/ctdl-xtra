import { z } from "zod";
import { publicProcedure, router } from ".";
import {
  findOrgsByUser
} from "../data/orgs";

export const orgsRouter = router({
  ofCurrentUser: publicProcedure
    .query(({ ctx: { user }}) => findOrgsByUser(user!.id)),
});
