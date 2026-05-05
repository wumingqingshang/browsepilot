/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,js}'],
  theme: {
    extend: {
      colors: {
        bg: '#faf9f6',
        surface: '#fefdfb',
        border: '#d4cdc2',
        'card-border': '#e8e0d4',
        'text-primary': '#1a1a1a',
        'text-body': '#4a4238',
        'text-muted': '#8b7f6e',
        'text-disabled': '#c4b5a5',
        accent: '#e33e2b',
      },
      fontFamily: {
        serif: ['Georgia', '"Times New Roman"', 'serif'],
      },
    },
  },
  plugins: [],
}
