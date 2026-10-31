import { createApp } from 'vue'
if (window.location.pathname.replace(/\/$/, '') === '/output') {
  const [{ default: OutputApp }] = await Promise.all([import('./output/OutputApp.vue'), import('./output/output.css')])
  createApp(OutputApp).mount('#app')
} else {
  const [{ default: App }] = await Promise.all([import('./App.vue'), import('./style.css')])
  createApp(App).mount('#app')
}
