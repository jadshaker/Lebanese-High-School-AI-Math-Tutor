/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        base: '#0a0a10',
        panel: '#111118',
        surface: '#1a1a28',
        hover: '#20203a',
        border: '#2a2a42',
        'border-active': '#3a3a5c',
        gold: {
          DEFAULT: '#f59e0b',
          dim: '#92610a',
          faint: '#1a1200',
        },
        indigo: {
          DEFAULT: '#818cf8',
          dim: '#3730a3',
          faint: '#0d0d2e',
        },
        emerald: {
          DEFAULT: '#34d399',
          faint: '#052015',
        },
        rose: {
          DEFAULT: '#f87171',
          faint: '#1f0808',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'thinking': 'thinking 1.4s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        thinking: {
          '0%, 80%, 100%': { transform: 'scale(0)', opacity: '0.5' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
