import "dotenv/config";
import { inspect } from "util";
import { CatalogueType } from "../../common/types";
import recursivelyDetectConfiguration from "./extraction/recursivelyDetectConfiguration";
import getLogger from "./logging";

const logger = getLogger("checkDetection");

async function testDetect(url: string) {
  const configuration = await recursivelyDetectConfiguration(
    url,
    CatalogueType.COURSES
  );
  logger.info(inspect(configuration));
  return configuration;
}

const url = process.argv[2];
testDetect(url);
