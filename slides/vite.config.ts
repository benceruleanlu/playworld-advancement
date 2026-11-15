import { defineConfig } from 'vite'

// Straight quotes and apostrophes in slide text (no typographic replacement).
export default defineConfig({
  slidev: {
    markdown: {
      markdownOptions: { typographer: false },
    },
  },
})
