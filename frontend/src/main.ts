// 高德地图 JS API 2.0 安全密钥必须在任何 AMap 代码执行前设置
// 2021年后创建的 key 必须配合 securityJsCode 使用，否则瓦片加载返回 400
; (window as any)._AMapSecurityConfig = {
  securityJsCode: import.meta.env.VITE_AMAP_SECURITY_CODE || ''
}

import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import Home from './views/Home.vue'
import Result from './views/Result.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Home',
      component: Home
    },
    {
      path: '/result',
      name: 'Result',
      component: Result
    }
  ]
})

const app = createApp(App)

app.use(router)
app.use(Antd)

app.mount('#app')

