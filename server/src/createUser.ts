import "dotenv/config";
import readline from "readline";
import { createUser, generateStrongPassword } from "./data/users";
import getLogger from "./logging";

const logger = getLogger("createUser");

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

rl.question("Enter email: ", (email) => {
  rl.question("Enter name: ", (name) => {
    const generatedPassword = generateStrongPassword(12);
    createUser(email, generatedPassword, name).then((user) => {
      logger.info({
        user,
        generatedPassword,
      });
      rl.close();
    });
  });
});
