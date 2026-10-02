/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",        // public site templates
    "./app/admin/templates/**/*.html",  // admin templates
    "./app/static/js/**/*.js",          // JS builds class names inside template literals
  ],
  // Classes that only ever appear as runtime strings (never as a literal in a
  // scanned file) must be listed here, otherwise the purge step drops them.
  safelist: [
    // toggled by the sidebar script in admin/base.html
    "-translate-x-full", "translate-x-0", "opacity-0", "opacity-100",
    "invisible", "hidden", "flex",
    // Alpine collapsible chevrons
    "rotate-90",
  ],
  theme: {
    extend: {
      screens: {
        'widescreen': {'raw': '(min-aspect-ratio: 3/2)'},
        'tallscreen': {'raw': '(min-aspect-ratio: 13/20)'},
      },
    },
  },
  plugins: [],
}
