import { cp, mkdir, rm, writeFile } from "node:fs/promises";

const outputDirectory = new URL("../mobile-dist/", import.meta.url);
const staticDirectory = new URL("../static/", import.meta.url);
const apiBaseUrl = (
  process.env.NOVA_API_BASE_URL || "https://video.byrongonzalez.dev"
).replace(/\/+$/, "");

if (!URL.canParse(apiBaseUrl) || new URL(apiBaseUrl).protocol !== "https:") {
  throw new Error("NOVA_API_BASE_URL must be an HTTPS URL");
}

await rm(outputDirectory, { force: true, recursive: true });
await mkdir(outputDirectory, { recursive: true });
await cp(staticDirectory, outputDirectory, { recursive: true });
await writeFile(
  new URL("config.js", outputDirectory),
  `window.NOVA_API_BASE_URL = ${JSON.stringify(apiBaseUrl)};\n`,
);
