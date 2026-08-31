import { createApp } from 'vue'
import { createPinia } from 'pinia'
// Fonts are bundled rather than pulled from fonts.googleapis.com. That link was
// a render-blocking stylesheet on a host that is unreachable from mainland
// China, so domestic visitors stared at a blank page until it timed out — and
// the site's whole audience is domestic recruiters. Self-hosting also means the
// first paint needs zero third-party origins, which keeps corporate proxies and
// the CSP in `deploy/Caddyfile` out of the critical path.
// Latin subsets only: none of these three faces ship CJK glyphs, so Chinese
// text falls through to the system stack declared in `styles/tokens.scss`.
import '@fontsource-variable/fraunces/wght.css'
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'
import 'ant-design-vue/dist/reset.css'
import './styles/index.scss'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
