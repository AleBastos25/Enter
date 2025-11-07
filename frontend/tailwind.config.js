/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'enter-orange': '#FF6B00',
        'enter-orange-hover': '#FF7A00',
        'bg-primary': '#000000',
        'bg-secondary': '#171717',
        'bg-tertiary': '#1f1f1f',
        'bg-card': '#2a2a2a',
        'text-primary': '#ffffff',
        'text-secondary': '#e5e5e5',
        'text-muted': '#9ca3af',
        'border-dark': '#404040',
      },
    },
  },
  plugins: [],
}
