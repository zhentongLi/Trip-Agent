<template>
  <div id="app">
    <a-layout style="min-height: 100vh">
      <!-- 顶部导航栏 -->
      <a-layout-header class="app-header">
        <div class="header-left">
          <span class="app-title" @click="$router.push('/')">🌍 HelloAgents 旅行助手</span>
        </div>
        <div class="header-right">
          <!-- 已登录 -->
          <template v-if="authState.token">
            <a-button type="text" class="nav-btn" @click="showCloudTrips = true">
              ☁️ 云端行程
            </a-button>
            <a-dropdown>
              <a-button type="text" class="nav-btn nav-user">
                👤 {{ authState.username }} ▾
              </a-button>
              <template #overlay>
                <a-menu>
                  <a-menu-item @click="handleLogout">🚪 退出登录</a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
          <!-- 未登录 -->
          <template v-else>
            <a-button type="text" class="nav-btn" @click="openAuth('login')">登录</a-button>
            <a-button type="primary" size="small" style="margin-left:8px" @click="openAuth('register')">注册</a-button>
          </template>
        </div>
      </a-layout-header>

      <a-layout-content style="padding: 24px">
        <router-view />
      </a-layout-content>

      <a-layout-footer style="text-align: center">
        HelloAgents 智能旅行助手 ©2026 基于 HelloAgents 框架
      </a-layout-footer>
    </a-layout>

    <!-- ── 登录/注册弹窗 ──────────────────────────────────────────── -->
    <a-modal
      v-model:open="authModalOpen"
      :title="authMode === 'login' ? '🔑 用户登录' : '📝 注册账号'"
      :footer="null"
      width="400px"
      @cancel="authModalOpen = false"
    >
      <!-- 登录表单 -->
      <a-form v-if="authMode === 'login'" :model="loginForm" layout="vertical" @finish="handleLogin">
        <a-form-item label="用户名" name="username" :rules="[{ required: true }]">
          <a-input v-model:value="loginForm.username" placeholder="请输入用户名" />
        </a-form-item>
        <a-form-item label="密码" name="password" :rules="[{ required: true }]">
          <a-input-password v-model:value="loginForm.password" placeholder="请输入密码" />
        </a-form-item>
        <a-button type="primary" html-type="submit" block :loading="authLoading">登录</a-button>
        <div style="text-align:center;margin-top:12px">
          <a-button type="link" @click="authMode = 'register'">没有账号？去注册</a-button>
        </div>
      </a-form>

      <!-- 注册表单 -->
      <a-form v-else :model="registerForm" layout="vertical" @finish="handleRegister">
        <a-form-item label="用户名" name="username" :rules="[{ required: true, min: 2 }]">
          <a-input v-model:value="registerForm.username" placeholder="2-32个字符" />
        </a-form-item>
        <a-form-item label="邮箱" name="email" :rules="[{ required: true, type: 'email' }]">
          <a-input v-model:value="registerForm.email" placeholder="your@email.com" />
        </a-form-item>
        <a-form-item label="密码" name="password" :rules="[{ required: true, min: 6 }]">
          <a-input-password v-model:value="registerForm.password" placeholder="至少6位" />
        </a-form-item>
        <a-button type="primary" html-type="submit" block :loading="authLoading">注册</a-button>
        <div style="text-align:center;margin-top:12px">
          <a-button type="link" @click="authMode = 'login'">已有账号？去登录</a-button>
        </div>
      </a-form>
    </a-modal>

    <!-- ── 云端行程抽屉 ───────────────────────────────────────────── -->
    <a-drawer
      v-model:open="showCloudTrips"
      title="☁️ 我的云端行程"
      placement="right"
      :width="380"
      @after-open-change="loadCloudTrips"
    >
      <template #extra>
        <a-button size="small" :loading="cloudLoading" @click="loadCloudTrips">🔄 刷新</a-button>
      </template>

      <a-spin :spinning="cloudLoading">
        <a-empty v-if="!cloudLoading && cloudTrips.length === 0" description="暂无云端行程，在行程结果页保存即可">
          <template #image><div style="font-size:40px">☁️</div></template>
        </a-empty>

        <a-list :data-source="cloudTrips" item-layout="horizontal">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta
                :title="item.title"
                :description="`${item.city} · ${item.created_at.slice(0,10)}`"
              />
              <template #actions>
                <a-button type="link" size="small" @click="loadCloudDetail(item.id)">加载</a-button>
                <a-popconfirm title="确认删除此行程？" @confirm="deleteCloud(item.id)">
                  <a-button type="link" size="small" danger>删除</a-button>
                </a-popconfirm>
              </template>
            </a-list-item>
          </template>
        </a-list>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { authState, setAuth, clearAuth } from '@/services/auth'
import { loginUser, registerUser, getUserTrips, getUserTripDetail, deleteUserTrip } from '@/services/api'
import type { SavedTripOut } from '@/types'

const router = useRouter()

// ── Auth 弹窗 ─────────────────────────────────────────────────────────────
const authModalOpen = ref(false)
const authMode = ref<'login' | 'register'>('login')
const authLoading = ref(false)
const loginForm = ref({ username: '', password: '' })
const registerForm = ref({ username: '', email: '', password: '' })

function openAuth(mode: 'login' | 'register') {
  authMode.value = mode
  authModalOpen.value = true
}

async function handleLogin() {
  authLoading.value = true
  try {
    const result = await loginUser(loginForm.value)
    setAuth(result.access_token, result.username, result.user_id)
    authModalOpen.value = false
    message.success(`欢迎回来，${result.username}！`)
    loginForm.value = { username: '', password: '' }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '登录失败')
  } finally {
    authLoading.value = false
  }
}

async function handleRegister() {
  authLoading.value = true
  try {
    const result = await registerUser(registerForm.value)
    setAuth(result.access_token, result.username, result.user_id)
    authModalOpen.value = false
    message.success(`注册成功，欢迎 ${result.username}！`)
    registerForm.value = { username: '', email: '', password: '' }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '注册失败')
  } finally {
    authLoading.value = false
  }
}

function handleLogout() {
  clearAuth()
  message.info('已退出登录')
}

// ── 云端行程 Drawer ────────────────────────────────────────────────────────
const showCloudTrips = ref(false)
const cloudLoading = ref(false)
const cloudTrips = ref<SavedTripOut[]>([])

async function loadCloudTrips() {
  if (!authState.token) return
  cloudLoading.value = true
  try {
    cloudTrips.value = await getUserTrips(authState.token)
  } catch (e: any) {
    message.error('加载云端行程失败')
  } finally {
    cloudLoading.value = false
  }
}

async function loadCloudDetail(tripId: number) {
  if (!authState.token) return
  try {
    const detail = await getUserTripDetail(tripId, authState.token)
    const plan = JSON.parse(detail.plan_json)
    sessionStorage.setItem('tripPlan', JSON.stringify(plan))
    showCloudTrips.value = false
    message.success('行程已加载！')

    // 当前已在结果页时，不走路由重载，改为页面内数据刷新
    if (router.currentRoute.value.path === '/result') {
      window.dispatchEvent(new CustomEvent('trip-plan-updated'))
    } else {
      await router.push('/result')
    }
  } catch (e: any) {
    message.error('加载行程详情失败')
  }
}

async function deleteCloud(tripId: number) {
  if (!authState.token) return
  try {
    await deleteUserTrip(tripId, authState.token)
    cloudTrips.value = cloudTrips.value.filter(t => t.id !== tripId)
    message.success('已删除')
  } catch (e: any) {
    message.error('删除失败')
  }
}
</script>

<style>
#app {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    'Noto Sans', sans-serif;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #001529;
  padding: 0 32px;
}

.header-left .app-title {
  color: white;
  font-size: 20px;
  font-weight: bold;
  cursor: pointer;
  transition: opacity 0.2s;
}
.header-left .app-title:hover { opacity: 0.8; }

.header-right { display: flex; align-items: center; gap: 4px; }

.nav-btn { color: rgba(255,255,255,0.85) !important; }
.nav-btn:hover { color: white !important; background: rgba(255,255,255,0.1) !important; }
.nav-user { font-weight: 500; }
</style>

