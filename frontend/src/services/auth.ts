/**
 * 功能18：轻量级用户认证状态管理（无 Pinia，用 reactive）
 * 全局单例，在任意组件 import 即可共享状态
 */
import { reactive, readonly } from 'vue'

interface AuthState {
    token: string | null
    username: string | null
    userId: number | null
}

const _STORAGE_KEY = 'trip_auth'

function _load(): AuthState {
    try {
        const raw = localStorage.getItem(_STORAGE_KEY)
        if (raw) return JSON.parse(raw)
    } catch { }
    return { token: null, username: null, userId: null }
}

const _state = reactive<AuthState>(_load())

function _persist() {
    localStorage.setItem(_STORAGE_KEY, JSON.stringify(_state))
}

export const authState = readonly(_state)

export function setAuth(token: string, username: string, userId: number) {
    _state.token = token
    _state.username = username
    _state.userId = userId
    _persist()
}

export function clearAuth() {
    _state.token = null
    _state.username = null
    _state.userId = null
    localStorage.removeItem(_STORAGE_KEY)
}

export function isLoggedIn(): boolean {
    return !!_state.token
}

export function getToken(): string | null {
    return _state.token
}
