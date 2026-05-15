<template>
  <div class="home">
    <!-- Background grid + glow blobs -->
    <div class="bg-grid" />
    <div class="bg-glow blob-1" />
    <div class="bg-glow blob-2" />

    <div class="home-inner">
      <!-- Hero -->
      <section class="hero">
        <div class="hero-badge">
          <span class="hero-badge-dot" />
          <span class="hero-badge-text">AI Travel Platform</span>
        </div>
        <h1 class="hero-title">
          智能规划<br />
          <span class="grad-text">每一次旅行</span>
        </h1>
        <p class="hero-subtitle">基于 LangGraph 多智能体 · SSE 实时流式生成 · 高德地图精准坐标</p>
        <button class="hero-history-btn" @click="openHistory">📋 历史行程</button>
      </section>

      <!-- City templates -->
      <section class="templates">
        <div class="eyebrow">热门城市快速选择</div>
        <div class="template-grid">
          <div
            v-for="tpl in cityTemplates"
            :key="tpl.city"
            class="template-card"
            @click="applyTemplate(tpl)"
          >
            <div class="tpl-icon">{{ tpl.icon }}</div>
            <div class="tpl-city">{{ tpl.city }}</div>
            <div class="tpl-desc">{{ tpl.desc }}</div>
            <div class="tpl-days-badge">{{ tpl.days }}天</div>
          </div>
        </div>
      </section>

      <!-- Form card -->
      <section class="form-card glass-card">
        <a-form :model="formData" layout="vertical" @finish="handleSubmit">
          <!-- ── Section 1: destination + dates -->
          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">📍</span>
              <span class="section-title">目的地与日期</span>
            </div>
            <a-row :gutter="12">
              <a-col :span="9">
                <div class="field-label">目的地城市</div>
                <a-input
                  v-model:value="formData.city"
                  placeholder="例如: 北京"
                  size="large"
                >
                  <template #prefix>🏙️</template>
                </a-input>
              </a-col>
              <a-col :span="6">
                <div class="field-label">开始日期</div>
                <a-date-picker
                  v-model:value="formData.start_date"
                  size="large"
                  style="width: 100%"
                  placeholder="选择日期"
                  :disabled-date="disabledStartDate"
                />
              </a-col>
              <a-col :span="6">
                <div class="field-label">结束日期</div>
                <a-date-picker
                  v-model:value="formData.end_date"
                  size="large"
                  style="width: 100%"
                  placeholder="选择日期"
                  :disabled-date="disabledEndDate"
                />
              </a-col>
              <a-col :span="3">
                <div class="field-label">天数</div>
                <div class="days-pill">
                  <span class="days-value">{{ formData.travel_days || '-' }}</span>
                  <span v-if="formData.travel_days > 0" class="days-unit">天</span>
                </div>
              </a-col>
            </a-row>
          </div>

          <!-- ── Section 2: preferences -->
          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">⚙️</span>
              <span class="section-title">偏好设置</span>
            </div>
            <a-row :gutter="16">
              <a-col :span="6">
                <div class="field-label">交通方式</div>
                <a-select v-model:value="formData.transportation" size="large" style="width:100%">
                  <a-select-option value="公共交通">🚇 公共交通</a-select-option>
                  <a-select-option value="自驾">🚗 自驾</a-select-option>
                  <a-select-option value="步行">🚶 步行</a-select-option>
                  <a-select-option value="混合">🔀 混合</a-select-option>
                </a-select>
              </a-col>
              <a-col :span="6">
                <div class="field-label">住宿偏好</div>
                <a-select v-model:value="formData.accommodation" size="large" style="width:100%">
                  <a-select-option value="经济型酒店">💰 经济型酒店</a-select-option>
                  <a-select-option value="舒适型酒店">🏨 舒适型酒店</a-select-option>
                  <a-select-option value="豪华酒店">⭐ 豪华酒店</a-select-option>
                  <a-select-option value="民宿">🏡 民宿</a-select-option>
                </a-select>
              </a-col>
              <a-col :span="12">
                <div class="field-label">旅行偏好</div>
                <div class="pref-tags">
                  <span
                    v-for="p in allPreferences"
                    :key="p"
                    class="pref-tag"
                    :class="{ checked: formData.preferences.includes(p) }"
                    @click="togglePref(p)"
                  >
                    {{ p }}
                  </span>
                </div>
              </a-col>
            </a-row>
          </div>

          <!-- ── Section 3: advanced -->
          <div class="form-section">
            <div class="section-header">
              <span class="section-icon">🎛️</span>
              <span class="section-title">高级设置（选填）</span>
            </div>
            <a-row :gutter="16">
              <a-col :span="8">
                <div class="field-label">💰 预算上限</div>
                <a-input-number
                  v-model:value="formData.budget_limit"
                  :min="100"
                  :max="100000"
                  :step="500"
                  placeholder="不填则不限"
                  size="large"
                  style="width: 100%"
                  addon-after="元"
                />
                <div class="field-hint">设置后 Agent 会优先推荐免票或低价景点</div>
              </a-col>
              <a-col :span="8">
                <div class="field-label">🌐 多城市联游</div>
                <div class="multi-city">
                  <a-switch
                    v-model:checked="multiCityMode"
                    checked-children="已开启"
                    un-checked-children="单城市"
                    @change="onMultiCityToggle"
                  />
                  <a-select
                    v-if="multiCityMode"
                    v-model:value="formData.cities"
                    mode="tags"
                    :token-separators="[',', '，', '→', ' ']"
                    placeholder="北京 → 西安 → 成都"
                    size="large"
                    style="width: 100%; margin-top: 8px"
                    :open="false"
                  />
                  <div v-if="multiCityMode" class="field-hint">按游览顺序输入，Agent 将生成跨城交通方案</div>
                </div>
              </a-col>
              <a-col :span="8">
                <div class="field-label">💬 额外要求</div>
                <a-textarea
                  v-model:value="formData.free_text_input"
                  placeholder="例如：想去看升旗、对海鲜过敏..."
                  :rows="2"
                />
              </a-col>
            </a-row>
          </div>

          <!-- Submit -->
          <a-button
            html-type="submit"
            class="submit-btn"
            :loading="loading"
            :disabled="loading"
            block
          >
            <template #icon><span v-if="!loading" class="submit-icon">🚀</span></template>
            {{ loading ? '正在生成中...' : '开始规划我的旅行' }}
          </a-button>

          <!-- Progress -->
          <div v-if="loading" class="loading-box">
            <div class="progress-track">
              <div class="progress-bar" :style="{ width: loadingProgress + '%' }" />
            </div>
            <div class="loading-status">{{ loadingStatus }}</div>
          </div>
        </a-form>
      </section>
    </div>
  </div>

  <!-- History drawer -->
  <a-drawer
    v-model:open="historyDrawerVisible"
    title="📋 最近行程历史（最多保存10条）"
    placement="right"
    :width="400"
  >
    <div style="margin-bottom: 12px; display:flex; justify-content:flex-end">
      <a-button danger size="small" @click="handleClearHistory">🗑️ 清空全部</a-button>
    </div>
    <div v-if="historyList.length === 0" class="history-empty">
      <div style="font-size: 48px; margin-bottom: 12px">📭</div>
      暂无历史记录，规划后自动保存
    </div>
    <a-list v-else :data-source="historyList" :split="false">
      <template #renderItem="{ item }">
        <a-list-item style="padding: 0; margin-bottom: 12px">
          <div class="history-card" @click="loadHistoryEntry(item)">
            <div class="history-card-head">
              <div class="history-title">{{ item.city }} {{ item.travel_days }}日游</div>
              <button class="history-delete" @click.stop="handleDeleteHistory(item.id)">✕</button>
            </div>
            <div class="history-date">📅 {{ item.start_date }} ~ {{ item.end_date }}</div>
            <div class="history-meta">🕐 {{ new Date(item.created_at).toLocaleString('zh-CN') }}</div>
          </div>
        </a-list-item>
      </template>
    </a-list>
  </a-drawer>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import dayjs from 'dayjs'
import { generateTripPlanStream, loadHistory, deleteHistoryEntry, clearHistory } from '@/services/api'
import type { TripFormData, TripHistoryEntry } from '@/types'
import type { Dayjs } from 'dayjs'

const router = useRouter()
const loading = ref(false)
const loadingProgress = ref(0)
const loadingStatus = ref('')

const multiCityMode = ref(false)
const historyDrawerVisible = ref(false)
const historyList = ref<TripHistoryEntry[]>([])

const cityTemplates = [
  { city: '北京', days: 3, icon: '🏗️', desc: '故宫/长城/天坛', preferences: ['历史文化', '美食'] },
  { city: '上海', days: 2, icon: '🌆', desc: '外滩/豫园/迪士尼', preferences: ['购物', '美食', '艺术'] },
  { city: '成都', days: 3, icon: '🐼', desc: '大熊猫/宽窄巷子', preferences: ['美食', '自然风光', '休闲'] },
  { city: '杭州', days: 2, icon: '🌸', desc: '西湖/灵隐寺', preferences: ['自然风光', '历史文化', '休闲'] },
  { city: '三亚', days: 3, icon: '🏖️', desc: '亚龙湾/天涯海角', preferences: ['自然风光', '休闲'] },
  { city: '西安', days: 3, icon: '🏚️', desc: '兵马俑/回民街', preferences: ['历史文化', '美食'] },
]

const allPreferences = ['历史文化', '自然风光', '美食', '购物', '艺术', '休闲', '亲子游', '蜜月', '摄影', '徒步', '夜生活']

const applyTemplate = (tpl: typeof cityTemplates[0]) => {
  formData.city = tpl.city
  formData.preferences = [...tpl.preferences]
  const start = dayjs().add(1, 'day')
  formData.start_date = start
  formData.end_date = start.add(tpl.days - 1, 'day')
  formData.travel_days = tpl.days
  message.success(`已应用"${tpl.city}${tpl.days}日游"模板`)
}

const togglePref = (pref: string) => {
  if (formData.preferences.includes(pref)) {
    formData.preferences = formData.preferences.filter(p => p !== pref)
  } else {
    formData.preferences = [...formData.preferences, pref]
  }
}

const disabledStartDate = (date: Dayjs) => date.isBefore(dayjs(), 'day')
const disabledEndDate = (date: Dayjs) => {
  if (formData.start_date) return date.isBefore(formData.start_date, 'day')
  return date.isBefore(dayjs(), 'day')
}

const formData = reactive<{
  city: string
  start_date: Dayjs | null
  end_date: Dayjs | null
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
  budget_limit: number | null
  cities: string[]
}>({
  city: '',
  start_date: null,
  end_date: null,
  travel_days: 1,
  transportation: '公共交通',
  accommodation: '经济型酒店',
  preferences: [],
  free_text_input: '',
  budget_limit: null,
  cities: [],
})

watch([() => formData.start_date, () => formData.end_date], ([start, end]) => {
  if (start && end) {
    const days = end.diff(start, 'day') + 1
    if (days > 0 && days <= 30) {
      formData.travel_days = days
    } else if (days > 30) {
      message.warning('旅行天数不能超过30天')
      formData.end_date = null
    } else {
      message.warning('结束日期不能早于开始日期')
      formData.end_date = null
    }
  }
})

const handleSubmit = async () => {
  if (!formData.city.trim() && (!formData.cities || formData.cities.length === 0)) {
    message.error('请输入目的地城市')
    return
  }
  if (!formData.start_date || !formData.end_date) {
    message.error('请选择日期')
    return
  }
  if (formData.travel_days > 30) {
    message.error('旅行天数不能超过30天')
    return
  }

  loading.value = true
  loadingProgress.value = 0
  loadingStatus.value = '正在初始化...'

  try {
    const primaryCity = (multiCityMode.value && formData.cities.length > 0)
      ? formData.cities[0]
      : formData.city

    const requestData: TripFormData = {
      city: primaryCity,
      start_date: formData.start_date.format('YYYY-MM-DD'),
      end_date: formData.end_date.format('YYYY-MM-DD'),
      travel_days: formData.travel_days,
      transportation: formData.transportation,
      accommodation: formData.accommodation,
      preferences: formData.preferences,
      free_text_input: formData.free_text_input,
      budget_limit: formData.budget_limit ?? undefined,
      cities: (multiCityMode.value && formData.cities.length >= 2) ? formData.cities : undefined,
    }

    await generateTripPlanStream(
      requestData,
      (evt) => {
        loadingProgress.value = evt.percent
        loadingStatus.value = evt.message
      },
      (plan) => {
        sessionStorage.setItem('tripPlan', JSON.stringify(plan))
        message.success('旅行计划生成成功！')
        loadingProgress.value = 100
        loadingStatus.value = '✅ 完成！'
        setTimeout(() => router.push('/result'), 400)
      },
      (msg) => {
        message.error(`生成失败: ${msg}`)
        loading.value = false
      }
    )
  } catch (error: any) {
    message.error(error.message || '生成旅行计划失败，请稍后重试')
  } finally {
    setTimeout(() => {
      loading.value = false
      loadingProgress.value = 0
      loadingStatus.value = ''
    }, 1200)
  }
}

const onMultiCityToggle = (checked: boolean) => {
  if (!checked) formData.cities = []
  else if (formData.city) formData.cities = [formData.city]
}

const openHistory = () => {
  historyList.value = loadHistory()
  historyDrawerVisible.value = true
}

const loadHistoryEntry = (entry: TripHistoryEntry) => {
  sessionStorage.setItem('tripPlan', JSON.stringify(entry.plan))
  historyDrawerVisible.value = false
  router.push('/result')
}

const handleDeleteHistory = (id: string) => {
  deleteHistoryEntry(id)
  historyList.value = loadHistory()
}

const handleClearHistory = () => {
  clearHistory()
  historyList.value = []
  message.success('历史记录已清空')
}
</script>

<style scoped>
.home {
  min-height: 100%;
  background: var(--bg-base);
  position: relative;
  /* 只裁剪水平方向（防止 glow blob 横向溢出），不裁剪垂直方向（保证页面可滚动） */
  overflow-x: clip;
  flex: 1;
}

.blob-1 {
  top: -120px;
  left: -80px;
  width: 500px;
  height: 500px;
  background: rgba(102, 126, 234, 0.12);
}
.blob-2 {
  top: 30%;
  right: -100px;
  width: 360px;
  height: 360px;
  background: rgba(118, 75, 162, 0.1);
}

.home-inner {
  position: relative;
  z-index: 1;
  padding: 52px 24px 40px;
  max-width: 960px;
  margin: 0 auto;
  animation: fadeInUp 0.6s ease-out;
}

/* Hero */
.hero {
  text-align: center;
  margin-bottom: 44px;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(102, 126, 234, 0.1);
  border: 1px solid rgba(102, 126, 234, 0.3);
  border-radius: 20px;
  padding: 5px 16px;
  margin-bottom: 20px;
}
.hero-badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-primary);
  box-shadow: 0 0 6px var(--brand-primary);
}
.hero-badge-text {
  font-size: 11px;
  color: rgba(102, 126, 234, 0.9);
  font-weight: 600;
  letter-spacing: 2px;
  text-transform: uppercase;
}
.hero-title {
  font-size: 52px;
  font-weight: 800;
  color: white;
  letter-spacing: -1px;
  line-height: 1.05;
  margin: 0;
}
.hero-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin-top: 14px;
  letter-spacing: 0.5px;
  font-weight: 300;
}
.hero-history-btn {
  margin-top: 16px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 20px;
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  padding: 6px 18px;
  transition: all 0.2s;
}
.hero-history-btn:hover {
  border-color: var(--border-brand-hover);
  color: var(--text-primary);
}

/* Templates */
.templates { margin-bottom: 28px; }
.templates .eyebrow { margin-bottom: 12px; }
.template-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
}
.template-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 12px 10px;
  cursor: pointer;
  text-align: center;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;
}
.template-card:hover {
  background: rgba(102, 126, 234, 0.12);
  border-color: rgba(102, 126, 234, 0.4);
  transform: translateY(-2px);
}
.tpl-icon { font-size: 24px; margin-bottom: 6px; }
.tpl-city {
  font-size: 13px;
  font-weight: 700;
  color: white;
}
.tpl-desc {
  font-size: 10px;
  color: var(--text-faint);
  margin-top: 2px;
}
.tpl-days-badge {
  margin-top: 6px;
  display: inline-block;
  background: rgba(102, 126, 234, 0.2);
  border: 1px solid rgba(102, 126, 234, 0.3);
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 10px;
  color: #a5b4fc;
  font-weight: 600;
}

/* Form card */
.form-card {
  padding: 24px;
}

.form-section {
  margin-bottom: 20px;
  padding: 16px 18px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 14px;
  border: 1px solid rgba(102, 126, 234, 0.1);
  position: relative;
  overflow: hidden;
}
.form-section::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(102,126,234,0.4), transparent);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}
.section-icon { font-size: 16px; }
.section-title {
  font-size: 13px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.8);
  letter-spacing: 0.3px;
}

.field-label {
  font-size: 11px;
  color: var(--text-faint);
  margin-bottom: 6px;
  letter-spacing: 0.5px;
}
.field-hint {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.2);
  margin-top: 4px;
}

/* Days pill */
.days-pill {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand-gradient-soft);
  border: 1px solid rgba(102, 126, 234, 0.3);
  border-radius: 12px;
  gap: 4px;
}
.days-value {
  font-size: 22px;
  font-weight: 800;
  color: white;
}
.days-unit {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
}

/* Preference tags */
.pref-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pref-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 12px;
  cursor: pointer;
  border: 1.5px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.45);
  user-select: none;
  transition: all 0.18s ease;
}
.pref-tag:hover {
  border-color: rgba(102, 126, 234, 0.4);
  color: rgba(255, 255, 255, 0.75);
}
.pref-tag.checked {
  border-color: rgba(102, 126, 234, 0.6);
  background: rgba(102, 126, 234, 0.2);
  color: #a5b4fc;
  box-shadow: 0 0 8px rgba(102, 126, 234, 0.2);
}

.multi-city { display: flex; flex-direction: column; }

/* Submit button — override AntD primary styles for gradient effect */
.submit-btn,
.submit-btn:not([disabled]):hover,
.submit-btn:not([disabled]):focus,
.submit-btn:not([disabled]):active {
  height: 48px !important;
  border-radius: 24px !important;
  font-size: 14px !important;
  font-weight: 700 !important;
  border: none !important;
  background: var(--brand-gradient) !important;
  color: white !important;
  box-shadow: var(--brand-glow-sm) !important;
}
.submit-btn:not([disabled]):hover {
  box-shadow: 0 8px 28px rgba(102, 126, 234, 0.55) !important;
  transform: translateY(-2px);
}
.submit-btn[disabled],
.submit-btn.ant-btn-loading {
  opacity: 0.7 !important;
  background: var(--brand-gradient) !important;
  color: white !important;
}
.submit-icon { font-size: 16px; }

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

/* Loading box */
.loading-box {
  margin-top: 16px;
  padding: 16px;
  background: rgba(102, 126, 234, 0.08);
  border-radius: 14px;
  border: 1px solid rgba(102, 126, 234, 0.2);
  text-align: center;
}
.progress-track {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  height: 6px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: var(--brand-gradient);
  border-radius: 8px;
  transition: width 0.4s ease;
  box-shadow: var(--brand-glow-sm);
}
.loading-status {
  color: #a5b4fc;
  font-size: 13px;
  font-weight: 500;
  margin-top: 8px;
}

/* History drawer */
.history-empty {
  text-align: center;
  color: var(--text-muted);
  padding: 60px 0;
}
.history-card {
  width: 100%;
  padding: 14px 16px;
  background: var(--surface-glass-strong);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}
.history-card:hover {
  border-color: var(--border-brand-hover);
  background: var(--surface-glass-hover);
  transform: translateY(-1px);
}
.history-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.history-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.history-delete {
  background: none;
  border: none;
  color: #ff8080;
  font-size: 14px;
  padding: 2px 6px;
  border-radius: 4px;
}
.history-delete:hover {
  background: rgba(255, 77, 79, 0.1);
}
.history-date {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 2px 0;
}
.history-meta {
  font-size: 11px;
  color: var(--text-faint);
}

/* Responsive */
@media (max-width: 768px) {
  .template-grid { grid-template-columns: repeat(3, 1fr); }
  .hero-title { font-size: 36px; }
  .home-inner { padding: 32px 16px; }
}
</style>
