// 类型定义

export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  ticket_price?: number
  opening_hours?: string   // #12 实时开放时间
}

export interface Meal {
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  name: string
  address?: string
  location?: Location
  description?: string
  estimated_cost?: number
}

export interface Hotel {
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost?: number
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
}

export interface WeatherInfo {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number
  night_temp: number
  wind_direction: string
  wind_power: string
  weather_warning?: string   // #13 天气预警
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
}

export interface TripFormData {
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
  budget_limit?: number       // #10 预算优化器
  cities?: string[]           // #11 多城市联游
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
}

// #9 历史记录条目
export interface TripHistoryEntry {
  id: string
  city: string
  start_date: string
  end_date: string
  travel_days: number
  created_at: string
  plan: TripPlan
}

// 功能20：AI 行程调整请求
export interface TripAdjustRequest {
  trip_plan: TripPlan
  user_message: string
  city?: string
}

// 功能20：AI 对话历史条目
export interface AdjustChatEntry {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

// 功能21：行程分享响应
export interface ShareCreateResponse {
  success: boolean
  share_id: string
  share_url: string
  expires_at: string
  message: string
}

// 功能18/23：用户账号系统
export interface TokenResponse {
  access_token: string
  token_type: string
  username: string
  user_id: number
}

export interface UserRegisterRequest {
  username: string
  email: string
  password: string
}

export interface UserLoginRequest {
  username: string
  password: string
}

export interface SavedTripOut {
  id: number
  city: string
  title: string
  created_at: string
}

export interface SavedTripDetail {
  id: number
  city: string
  title: string
  plan_json: string
  created_at: string
}

// 功能27：导游RAG模式
export interface GuideReference {
  title: string
  city: string
  attraction_name: string
  snippet: string
  source: string
  score: number
}

export interface GuideAskRequest {
  question: string
  session_id?: string
  debug?: boolean
  city?: string
  attraction_name?: string
  trip_plan?: TripPlan
  top_k?: number
}

export interface GuideDebugSkillMeta {
  skill_name?: string
  skill_description?: string
  session_id?: string
  debug?: boolean
}

export interface GuideDebugRetrievalMeta {
  rewritten_queries?: string[]
  iterative_rounds?: number
  source_counts?: Record<string, number>
  has_local_kb_hit?: boolean
  vector_store_enabled?: boolean
  embedding_strategy?: string
  reranker_mode?: string
}

export interface GuideDebugMeta {
  skill_meta?: GuideDebugSkillMeta
  retrieval_meta?: GuideDebugRetrievalMeta
}

export interface GuideAskResponse {
  success: boolean
  answer: string
  references: GuideReference[]
  debug_meta?: GuideDebugMeta | null
  message: string
}

