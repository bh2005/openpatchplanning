import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import LoginView from './views/LoginView.vue'
import Dashboard from './views/Dashboard.vue'
import Sites from './views/Sites.vue'
import Devices from './views/Devices.vue'
import DeviceDetail from './views/DeviceDetail.vue'
import Racks from './views/Racks.vue'
import ImportView from './views/ImportView.vue'
import Admin from './views/Admin.vue'
import Help from './views/Help.vue'
import WorkOrderList from './views/WorkOrderList.vue'
import WorkOrderDetail from './views/WorkOrderDetail.vue'
import { isLoggedIn, isAdmin, hasRole } from './api.js'
import { helpContext } from './content/helpContext.js'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',            redirect: '/dashboard' },
    { path: '/login',       component: LoginView, meta: { public: true } },
    { path: '/dashboard',   component: Dashboard },
    { path: '/sites',       component: Sites },
    { path: '/devices',     component: Devices },
    { path: '/devices/:id', component: DeviceDetail },
    { path: '/racks',       component: Racks },
    { path: '/workorders',    component: WorkOrderList },
    { path: '/workorders/:id', component: WorkOrderDetail },
    { path: '/import',      component: ImportView, meta: { admin: true } },
    { path: '/admin',       component: Admin, meta: { admin: true } },
    { path: '/handbuch',    component: Help },
  ],
})

router.beforeEach(to => {
  if (!to.meta.public && !isLoggedIn()) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.meta.admin && !isAdmin()) return { path: '/dashboard' }
})

router.afterEach(() => { helpContext.value = '' })

createApp(App).use(router).mount('#app')
