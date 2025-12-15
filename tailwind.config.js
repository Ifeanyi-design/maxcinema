/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",       // existing templates
    "./app/admin/templates/**/*.html", // add this for admin templates
    "./static/js/**/*.js",         // JS files
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
