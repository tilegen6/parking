/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Палитра укоренена в казахстанском номере/флаге.
        ink: {
          DEFAULT: "#0B1B2B", // navy-чернила: hero, текст
          700: "#12283B",
          600: "#1B3A52",
          500: "#2A506E",
        },
        sky: {
          DEFAULT: "#00A6C8", // голубой полосы «KZ» — основной
          600: "#0089A6",
          700: "#0B7186",
          400: "#3CC3DE",
          100: "#D6F1F7",
        },
        gold: {
          DEFAULT: "#F4B400", // золото флага — акцент (live/выручка)
          600: "#D69A00",
        },
        paper: "#F4F6F2", // тёплая бумага — фон
        surface: "#FFFFFF",
        line: "#E3E7E0",
        // brand → sky, чтобы существующие страницы переняли новый основной цвет
        brand: {
          DEFAULT: "#00A6C8",
          dark: "#0B7186",
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(11,27,43,0.04), 0 8px 24px -12px rgba(11,27,43,0.12)",
        hero: "0 24px 60px -28px rgba(0,166,200,0.55)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "70%": { transform: "scale(2.2)", opacity: "0" },
          "100%": { opacity: "0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s ease-out both",
        "pulse-ring": "pulse-ring 1.8s ease-out infinite",
      },
    },
  },
  plugins: [],
};
