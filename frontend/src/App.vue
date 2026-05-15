<template>
  <div id="app">
    <!-- ── Dark tech top navigation ─────────────────────────────────── -->
    <header class="app-header">
      <!-- scan line glow -->
      <div class="scan-line" />

      <div class="brand" @click="$router.push('/')">
        <div class="brand-icon">🌍</div>
        <span class="brand-title">任我行</span>
        <span class="brand-badge">AI</span>
      </div>

      <nav class="nav-links">
        <div
          v-for="item in navLinks"
          :key="item.to"
          class="nav-link"
          :class="{ active: $route.path === item.to }"
          @click="$router.push(item.to)"
        >
          <span class="nav-link-active-bar" v-if="$route.path === item.to" />
          {{ item.label }}
        </div>
      </nav>

      <div class="header-spacer" />

      <!-- AI status pill -->
      <div class="status-pill">
        <div class="status-dot" />
        <span>AI 在线</span>
      </div>

      <template v-if="authState.token">
        <button class="nav-btn" @click="showCloudTrips = true">☁️ 云端行程</button>
        <a-dropdown :trigger="['click']">
          <button class="nav-btn nav-user">
            👤 {{ authState.username }} ▾
          </button>
          <template #overlay>
            <a-menu @click="handleMenuClick">
              <a-menu-item key="logout">🚪 退出登录</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </template>
      <template v-else>
        <button class="nav-btn" @click="openAuth('login')">登录</button>
        <button class="nav-btn-primary" @click="openAuth('register')">注册</button>
      </template>
    </header>

    <main class="app-main">
      <router-view />
    </main>

    <!-- ── 登录/注册弹窗 ─────────────────────────────────────────── -->
    <a-modal
      v-model:open="authModalOpen"
      :title="authMode === 'login' ? '🔑 用户登录' : '📝 注册账号'"
      :footer="null"
      width="400px"
      @cancel="authModalOpen = false"
    >
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

    <!-- ── 云端行程抽屉 ─────────────────────────────────────────── -->
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
            <a-list-item class="cloud-trip-item">
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

const navLinks = [
  { to: '/', label: '规划行程' },
  { to: '/result', label: '我的行程' },
]

// ── Auth modal ───────────────────────────────────────────────────────────
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

function handleMenuClick({ key }: { key: string }) {
  if (key === 'logout') handleLogout()
}

// ── Cloud trips drawer ────────────────────────────────────────────────────
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

<style scoped>
#app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-base);
}

/* ── Header ─────────────────────────────────────────────────────────── */
.app-header {
  height: 52px;
  background: rgba(8, 8, 16, 0.95);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border-brand);
  display: flex;
  align-items: center;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 100;
  flex-shrink: 0;
}

.scan-line {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, #667eea 40%, #a78bfa 60%, transparent);
  opacity: 0.5;
  pointer-events: none;
  animation: scan-line 3s ease-in-out infinite;
}

/* Brand */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  margin-right: 32px;
  user-select: none;
}
.brand-icon {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--brand-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  box-shadow: var(--brand-glow);
}
.brand-title {
  color: white;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.brand-badge {
  font-size: 9px;
  color: rgba(102, 126, 234, 0.8);
  border: 1px solid rgba(102, 126, 234, 0.3);
  border-radius: 4px;
  padding: 1px 6px;
  letter-spacing: 1.5px;
  font-weight: 600;
}

/* Nav links */
.nav-links {
  display: flex;
  height: 100%;
  align-items: center;
}
.nav-link {
  height: 100%;
  display: flex;
  align-items: center;
  padding: 0 16px;
  font-size: 12px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.35);
  position: relative;
  transition: color 0.2s;
}
.nav-link:hover { color: var(--text-secondary); }
.nav-link.active { color: white; }
.nav-link-active-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--brand-gradient);
  box-shadow: var(--brand-glow-sm);
}

.header-spacer { flex: 1; }

/* AI status pill */
.status-pill {
  display: flex;
  align-items: center;
  gap: 5px;
  background: rgba(52, 199, 89, 0.1);
  border: 1px solid rgba(52, 199, 89, 0.25);
  border-radius: 20px;
  padding: 3px 10px;
  margin-right: 10px;
}
.status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #34c759;
  box-shadow: 0 0 6px #34c759;
}
.status-pill span {
  font-size: 10px;
  color: rgba(52, 199, 89, 0.85);
  font-weight: 600;
  letter-spacing: 0.5px;
}

/* Header buttons */
.nav-btn {
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text-secondary);
  font-size: 11px;
  margin-left: 4px;
  transition: all 0.18s;
}
.nav-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--text-primary);
}
.nav-user { font-weight: 500; }

.nav-btn-primary {
  height: 30px;
  padding: 0 14px;
  border-radius: 8px;
  background: var(--brand-gradient);
  border: none;
  color: white;
  font-size: 11px;
  font-weight: 700;
  margin-left: 6px;
  box-shadow: var(--brand-glow-sm);
  transition: all 0.2s;
}
.nav-btn-primary:hover {
  box-shadow: var(--brand-glow);
  transform: translateY(-1px);
}

/* Main — 不裁剪溢出，让 Home 页内容撑开 body（body 级滚动） */
.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
}

/* Cloud trip drawer items */
.cloud-trip-item :deep(.ant-list-item-meta-title) {
  color: var(--text-primary) !important;
}
.cloud-trip-item :deep(.ant-list-item-meta-description) {
  color: var(--text-muted) !important;
}
</style>
