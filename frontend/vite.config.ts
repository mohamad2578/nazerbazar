import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// eslint-disable-next-line
const backend = (globalThis as any).process?.env?.BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "ناظر ۷۲۴ — شفافیت قیمت کالاهای اساسی",
        short_name: "ناظر ۷۲۴",
        description: "مقایسه قیمت کالاهای اساسی در فروشگاه‌های مجاز و ثبت تخلف",
        lang: "fa",
        dir: "rtl",
        start_url: "/",
        display: "standalone",
        background_color: "#f6f7f5",
        theme_color: "#0f766e",
        icons: [
          { src: "pwa-192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api/, /^\/media/, /^\/django-admin/],
        runtimeCaching: [
          {
            // داده‌های عمومی: شبکه اول، در قطعی اینترنت آخرین نسخه نمایش داده می‌شود
            urlPattern: ({ url }) => url.pathname.startsWith("/api/public/"),
            handler: "NetworkFirst",
            options: { cacheName: "public-api", networkTimeoutSeconds: 6, expiration: { maxEntries: 200, maxAgeSeconds: 86400 } },
          },
          {
            urlPattern: ({ url }) => url.pathname.startsWith("/media/"),
            handler: "CacheFirst",
            options: { cacheName: "media", expiration: { maxEntries: 300, maxAgeSeconds: 604800 } },
          },
          {
            urlPattern: ({ url }) => url.hostname.includes("tile"),
            handler: "StaleWhileRevalidate",
            options: { cacheName: "map-tiles", expiration: { maxEntries: 500, maxAgeSeconds: 1209600 } },
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: { "/api": backend, "/media": backend, "/django-admin": backend, "/static": backend },
  },
  build: { chunkSizeWarningLimit: 900 },
});
