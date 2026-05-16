import { env } from "./config/env.js";
import { buildApp } from "./server/app.js";
import { prisma } from "./db/prisma.js";

const app = await buildApp();

const shutdown = async () => {
  app.log.info("Shutting down...");
  await app.close();
  await prisma.$disconnect();
  process.exit(0);
};

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

await app.listen({ port: env.PORT, host: "0.0.0.0" });
