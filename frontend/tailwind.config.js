/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: '#0F172A',
        // DEFAULT keeps every existing bare `emerald` / `emerald/NN` opacity
        // usage (brand color) resolving exactly as before; the numbered
        // shades (standard Tailwind emerald scale) are additive, used by the
        // chat markdown chip/callout styling in `MarkdownMessage.jsx`.
        emerald: {
          DEFAULT: '#059669',
          50: '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
          950: '#022c22',
        },
        gold: '#D97706',
        'bg-soft': '#F8FAFC',
      },
    },
  },
  plugins: [],
}
