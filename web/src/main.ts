import { createApp } from 'vue'
if (window.location.pathname.replace(/\/$/, '') === '/avatar3d') {
  const [{ default: AvatarLab }] = await Promise.all([import('./avatar3d/AvatarLab.vue'), import('./avatar3d/avatar3d.css')])
  createApp(AvatarLab).mount('#app')
} else if (window.location.pathname.replace(/\/$/, '') === '/output') {
  const [{ default: OutputApp }] = await Promise.all([import('./output/OutputApp.vue'), import('./output/output.css')])
  createApp(OutputApp).mount('#app')
} else {
  const [{ default: App }] = await Promise.all([import('./App.vue'), import('./style.css')])
  createApp(App).mount('#app')
}
