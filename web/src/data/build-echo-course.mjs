/** Copy the canonical API dialogue course into Vite's deployable source tree. */

import { readFile, writeFile } from "node:fs/promises";

const source = new URL("../../../api/data/echo_scenes.json", import.meta.url);
const destination = new URL("./echo-scenes.generated.json", import.meta.url);
const canonical = await readFile(source, "utf8");
const document = JSON.parse(canonical);

if (document.schema_version !== 2 || document.scenes?.length !== 4) {
  throw new Error("The canonical Echo course must contain four schema-v2 scenes.");
}

await writeFile(destination, canonical, "utf8");
console.log(`Bundled ${document.scenes.length} canonical Echo scenes.`);
