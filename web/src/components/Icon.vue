<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const paths: Record<string, string> = {
  studio: 'M3 5h18v12H3z M8 21h8 M12 17v4 M9 9l6 3-6 3z',
  box: 'M12 3 3 8l9 5 9-5-9-5z M3 8v9l9 5 9-5V8 M12 13v9 M7.5 5.5l9 5',
  person: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-2a8 8 0 0 1 16 0v2',
  book: 'M3 4h7a3 3 0 0 1 2 1 3 3 0 0 1 2-1h7v16h-7a3 3 0 0 0-2 1 3 3 0 0 0-2-1H3z M12 5v16',
  check: 'M20 6 9 17l-5-5',
  shield: 'M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7z M8 12l3 3 5-6',
  plus: 'M12 5v14 M5 12h14',
  close: 'M6 6l12 12 M18 6 6 18',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 5a8 8 0 0 1 14 7 M4 12a8 8 0 0 0 14 7',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  play: 'M8 4l13 8-13 8z',
  pause: 'M7 4h3v16H7z M14 4h3v16h-3z',
  sound: 'M3 9h4l5-4v14l-5-4H3z M16 8a6 6 0 0 1 0 8 M19 5a10 10 0 0 1 0 14',
  wave: 'M3 10v4 M7 6v12 M11 3v18 M15 7v10 M19 4v16 M23 10v4',
  bolt: 'M13 2 4 14h7l-1 8 10-13h-7z',
  logout: 'M9 3H4v18h5 M13 7l5 5-5 5 M8 12h13',
  edit: 'm15 4 5 5 M4 16 16 4l4 4L8 20H4z',
  trash: 'M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7',
  search: 'M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0 M15 15l6 6',
  clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2',
  lock: 'M5 10h14v11H5z M8 10V7a4 4 0 0 1 8 0v3 M12 14v3',
}
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.studio" /></svg></template>
