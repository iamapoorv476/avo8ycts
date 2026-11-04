/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        forecast: "#38BDF8", 
        actual: "#34D399", 
        floor: "#F59E0B", 
        over: "#F43F5E", 
        under: "#06B6D4", 
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};