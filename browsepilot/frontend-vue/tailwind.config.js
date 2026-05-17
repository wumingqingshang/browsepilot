/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,js}'],
  theme: {
    extend: {
      colors: {
        bg: '#faf9f6',
        surface: '#fefdfb',
        border: '#d4cdc2',
        'card-border': '#b8a99a',
        'text-primary': '#1a1a1a',
        'text-body': '#4a4238',
        'text-muted': '#8b7f6e',
        'text-muted-deep': '#6b5f52',
        'text-disabled': '#c4b5a5',
        accent: '#e33e2b',
      },
      fontFamily: {
        serif: ['Georgia', '"Times New Roman"', 'serif'],
        sans: ['system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
