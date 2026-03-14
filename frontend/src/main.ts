import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { vRipple } from './directives/ripple'

const app = createApp(App)
app.directive('ripple', vRipple)
app.use(router)
app.use(i18n)
app.mount('#app')
