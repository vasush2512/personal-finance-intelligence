import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    rollupOptions: {
      output: {
        /**
         * Split the vendor code out of the application bundle.
         *
         * Recharts and its d3 dependencies are roughly two-thirds of the
         * output and change only when the dependency is upgraded, while the
         * app code changes constantly. In one file, every edit to a page
         * invalidates the browser cache for all of it; split, a redeploy
         * re-downloads the small half and the large half is served from cache.
         *
         * Charts are also the one thing several pages do not use at all, so
         * this pairs with the lazy import in ChartLoader.
         */
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/]node_modules[\\/](recharts|d3-|victory|internmap|delaunator|robust-predicates)/.test(id)) {
            return "charts";
          }
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) {
            return "react";
          }
          return "vendor";
        },
      },
    },
  },
});
