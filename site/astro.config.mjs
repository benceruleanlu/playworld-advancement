// Static build for GitHub Pages at https://benceruleanlu.github.io/playworld-advancement/
import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://benceruleanlu.github.io",
  base: "/playworld-advancement",
  output: "static",
  build: { inlineStylesheets: "auto" },
});
