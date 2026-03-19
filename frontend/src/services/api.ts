import axios from 'axios'
import type {
  TripFormData, TripPlanResponse, TripPlan, TripHistoryEntry,
  TripAdjustRequest, ShareCreateResponse,
  TokenResponse, UserRegisterRequest, UserLoginRequest, SavedTripOut, SavedTripDetail,
  GuideAskRequest, GuideAskResponse,
} from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 2分钟超时
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 生成旅行计划（传统 JSON 接口，兼容旧代码）
 */
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

// ===================== #14 SSE 流式生成 =====================

export interface SSEProgressEvent {
  type: 'progress'
  percent: number
  message: string
}
export interface SSEDoneEvent {
  type: 'done'
  data: TripPlan
}
export interface SSEErrorEvent {
  type: 'error'
  message: string
}
export type SSEEvent = SSEProgressEvent | SSEDoneEvent | SSEErrorEvent

/**
 * 流式生成旅行计划（SSE）
 * @param formData 表单数据
 * @param onProgress 进度回调
 * @param onDone 完成回调，返回完整行程
 * @param onError 错误回调
 */
export async function generateTripPlanStream(
  formData: TripFormData,
  onProgress: (event: SSEProgressEvent) => void,
  onDone: (plan: TripPlan) => void,
  onError: (msg: string) => void
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/trip/plan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(formData),
  })

  if (!response.ok || !response.body) {
    throw new Error(`SSE 请求失败: ${response.status} ${response.statusText}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? '' // 最后一行可能是不完整的，保留给下次拼接

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue
      const jsonStr = trimmed.slice(5).trim()
      if (!jsonStr) continue

      try {
        const event: SSEEvent = JSON.parse(jsonStr)
        if (event.type === 'progress') {
          onProgress(event)
        } else if (event.type === 'done') {
          onDone(event.data)
        } else if (event.type === 'error') {
          onError(event.message)
        }
      } catch (e) {
        console.warn('SSE JSON 解析失败:', jsonStr, e)
      }
    }
  }
}

// ===================== #9 本地历史记录工具 =====================

const HISTORY_KEY = 'tripHistory'
const HISTORY_MAX = 10

/**
 * 保存一条历史记录到 localStorage（最多保留10条）
 */
export function saveHistory(plan: TripPlan): void {
  const entry: TripHistoryEntry = {
    id: Date.now().toString(36),
    city: plan.city,
    start_date: plan.start_date,
    end_date: plan.end_date,
    travel_days: plan.days.length,
    created_at: new Date().toISOString(),
    plan,
  }
  const raw = localStorage.getItem(HISTORY_KEY)
  const list: TripHistoryEntry[] = raw ? JSON.parse(raw) : []
  list.unshift(entry)               // 最新的放最前
  if (list.length > HISTORY_MAX) list.length = HISTORY_MAX
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list))
}

/**
 * 读取历史记录列表
 */
export function loadHistory(): TripHistoryEntry[] {
  const raw = localStorage.getItem(HISTORY_KEY)
  return raw ? JSON.parse(raw) : []
}

/**
 * 删除一条历史记录
 */
export function deleteHistoryEntry(id: string): void {
  const list = loadHistory().filter(e => e.id !== id)
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list))
}

/**
 * 清空所有历史记录
 */
export function clearHistory(): void {
  localStorage.removeItem(HISTORY_KEY)
}

// ===================== 分享相关 =====================

/**
 * 创建分享链接（功能21）
 */
export async function createShare(tripPlan: TripPlan, title?: string): Promise<ShareCreateResponse> {
  try {
    const response = await apiClient.post<ShareCreateResponse>('/api/trip/share', { plan: tripPlan, title })
    return response.data
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '创建分享链接失败')
  }
}

/**
 * 获取分享的旅行计划
 */
export async function getSharedTrip(shareId: string): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.get<TripPlanResponse>(`/api/trip/share/${shareId}`)
    return response.data
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || '获取分享行程失败')
  }
}

// ===================== 功能20：AI 行程调整 =====================

/**
 * AI 行程调整对话
 * @param tripPlan 当前行程
 * @param userMessage 用户调整要求
 * @returns 修改后的 TripPlan
 */
export async function adjustTripPlan(tripPlan: TripPlan, userMessage: string): Promise<TripPlan> {
  try {
    const body: TripAdjustRequest = {
      trip_plan: tripPlan,
      user_message: userMessage,
      city: tripPlan.city,
    }
    const response = await apiClient.post<TripPlanResponse>('/api/trip/adjust', body)
    if (response.data.success && response.data.data) {
      return response.data.data
    }
    throw new Error(response.data.message || 'AI 调整失败')
  } catch (error: any) {
    throw new Error(error.response?.data?.detail || error.message || 'AI 行程调整失败')
  }
}

/**
 * 功能22：后端 ReportLab PDF 导出
 * @param tripPlan 完整行程数据
 */
export async function exportTripPdfBackend(tripPlan: TripPlan): Promise<void> {
  const response = await apiClient.post('/api/trip/export/pdf', tripPlan, {
    responseType: 'blob',
    timeout: 30000,
  })
  const blob = new Blob([response.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `trip_${tripPlan.city}_${tripPlan.start_date}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * 功能18：用户注册
 */
export async function registerUser(data: UserRegisterRequest): Promise<TokenResponse> {
  const resp = await apiClient.post<TokenResponse>('/api/auth/register', data)
  return resp.data
}

/**
 * 功能18：用户登录
 */
export async function loginUser(data: UserLoginRequest): Promise<TokenResponse> {
  const resp = await apiClient.post<TokenResponse>('/api/auth/login', data)
  return resp.data
}

/**
 * 功能23：获取云端行程列表
 */
export async function getUserTrips(token: string): Promise<SavedTripOut[]> {
  const resp = await apiClient.get<SavedTripOut[]>('/api/user/trips', {
    headers: { Authorization: `Bearer ${token}` },
  })
  return resp.data
}

/**
 * 功能23：保存行程到云端
 */
export async function saveUserTrip(
  tripPlan: TripPlan,
  token: string,
  title?: string,
): Promise<SavedTripOut> {
  const body = { ...tripPlan, title: title || `${tripPlan.city} ${tripPlan.start_date} 行程` }
  const resp = await apiClient.post<SavedTripOut>('/api/user/trips', body, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return resp.data
}

/**
 * 功能23：获取云端行程详情（含 plan_json）
 */
export async function getUserTripDetail(tripId: number, token: string): Promise<SavedTripDetail> {
  const resp = await apiClient.get<SavedTripDetail>(`/api/user/trips/${tripId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return resp.data
}

/**
 * 功能23：删除云端行程
 */
export async function deleteUserTrip(tripId: number, token: string): Promise<void> {
  await apiClient.delete(`/api/user/trips/${tripId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

/**
 * 功能27：导游RAG问答
 */
export async function askGuideQuestion(data: GuideAskRequest): Promise<GuideAskResponse> {
  const resp = await apiClient.post<GuideAskResponse>('/api/guide/ask', data)
  return resp.data
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export default apiClient

