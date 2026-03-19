<template>
  <div class="home-container">
    <!-- 背景装饰 -->
    <div class="bg-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
      <div class="circle circle-3"></div>
    </div>

    <!-- 页面标题 -->
    <div class="page-header">
      <div class="icon-wrapper">
        <span class="icon">✈️</span>
      </div>
      <h1 class="page-title">智能旅行助手</h1>
      <p class="page-subtitle">基于AI的个性化旅行规划,让每一次出行都完美无忧</p>
      <!-- #9 历史记录入口 -->
      <div class="header-actions">
        <a-button ghost @click="openHistory" style="color: rgba(255,255,255,0.9); border-color: rgba(255,255,255,0.5);">
          📋 历史行程
        </a-button>
      </div>
    </div>

    <!-- 热门城市快速选择 -->
    <div class="templates-section">
      <div class="templates-title">🏙️ 热门城市快速选择</div>
      <div class="templates-grid">
        <div
          v-for="tpl in cityTemplates"
          :key="tpl.city"
          class="template-card"
          @click="applyTemplate(tpl)"
        >
          <span class="tpl-icon">{{ tpl.icon }}</span>
          <div class="tpl-info">
            <div class="tpl-city">{{ tpl.city }}</div>
            <div class="tpl-desc">{{ tpl.desc }}</div>
          </div>
          <div class="tpl-days">{{ tpl.days }}天</div>
        </div>
      </div>
    </div>

    <a-card class="form-card" :bordered="false">
      <a-form
        :model="formData"
        layout="vertical"
        @finish="handleSubmit"
      >
        <!-- 第一步:目的地和日期 -->
        <div class="form-section">
          <div class="section-header">
            <span class="section-icon">📍</span>
            <span class="section-title">目的地与日期</span>
          </div>

          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="city" :rules="[{ required: true, message: '请输入目的地城市' }]">
                <template #label>
                  <span class="form-label">目的地城市</span>
                </template>
                <a-input
                  v-model:value="formData.city"
                  placeholder="例如: 北京"
                  size="large"
                  class="custom-input"
                >
                  <template #prefix>
                    <span style="color: #1890ff;">🏙️</span>
                  </template>
                </a-input>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="start_date" :rules="[{ required: true, message: '请选择开始日期' }]">
                <template #label>
                  <span class="form-label">开始日期</span>
                </template>
                <a-date-picker
                  v-model:value="formData.start_date"
                  style="width: 100%"
                  size="large"
                  class="custom-input"
                  placeholder="选择日期"
                  :disabled-date="disabledStartDate"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="end_date" :rules="[{ required: true, message: '请选择结束日期' }]">
                <template #label>
                  <span class="form-label">结束日期</span>
                </template>
                <a-date-picker
                  v-model:value="formData.end_date"
                  style="width: 100%"
                  size="large"
                  class="custom-input"
                  placeholder="选择日期"
                  :disabled-date="disabledEndDate"
                />
              </a-form-item>
            </a-col>
            <a-col :span="4">
              <a-form-item>
                <template #label>
                  <span class="form-label">旅行天数</span>
                </template>
                <div class="days-display-compact">
                  <span class="days-value">{{ formData.travel_days }}</span>
                  <span class="days-unit">天</span>
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 第二步:偏好设置 -->
        <div class="form-section">
          <div class="section-header">
            <span class="section-icon">⚙️</span>
            <span class="section-title">偏好设置</span>
          </div>

          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="transportation">
                <template #label>
                  <span class="form-label">交通方式</span>
                </template>
                <a-select v-model:value="formData.transportation" size="large" class="custom-select">
                  <a-select-option value="公共交通">🚇 公共交通</a-select-option>
                  <a-select-option value="自驾">🚗 自驾</a-select-option>
                  <a-select-option value="步行">🚶 步行</a-select-option>
                  <a-select-option value="混合">🔀 混合</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item name="accommodation">
                <template #label>
                  <span class="form-label">住宿偏好</span>
                </template>
                <a-select v-model:value="formData.accommodation" size="large" class="custom-select">
                  <a-select-option value="经济型酒店">💰 经济型酒店</a-select-option>
                  <a-select-option value="舒适型酒店">🏨 舒适型酒店</a-select-option>
                  <a-select-option value="豪华酒店">⭐ 豪华酒店</a-select-option>
                  <a-select-option value="民宿">🏡 民宿</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item name="preferences">
                <template #label>
                  <span class="form-label">旅行偏好</span>
                </template>
                <div class="preference-tags">
                  <a-checkbox-group v-model:value="formData.preferences" class="custom-checkbox-group">
                    <a-checkbox value="历史文化" class="preference-tag">🏛️ 历史文化</a-checkbox>
                    <a-checkbox value="自然风光" class="preference-tag">🏞️ 自然风光</a-checkbox>
                    <a-checkbox value="美食" class="preference-tag">🍜 美食</a-checkbox>
                    <a-checkbox value="购物" class="preference-tag">🛍️ 购物</a-checkbox>
                    <a-checkbox value="艺术" class="preference-tag">🎨 艺术</a-checkbox>
                    <a-checkbox value="休闲" class="preference-tag">☕ 休闲</a-checkbox>                    <a-checkbox value="亲子游" class="preference-tag">👨‍👧 亲子游</a-checkbox>
                    <a-checkbox value="蜜月" class="preference-tag">💍 蜜月</a-checkbox>
                    <a-checkbox value="摄影" class="preference-tag">📷 摄影</a-checkbox>
                    <a-checkbox value="徒步" class="preference-tag">🥾 徒步</a-checkbox>
                    <a-checkbox value="夜生活" class="preference-tag">🎇 夜生活</a-checkbox>                  </a-checkbox-group>
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 第三步：高级设置（预算 + 多城市） -->
        <div class="form-section">
          <div class="section-header">
            <span class="section-icon">🎛️</span>
            <span class="section-title">高级设置（选填）</span>
          </div>
          <a-row :gutter="24">
            <!-- #10 预算优化器 -->
            <a-col :span="12">
              <a-form-item name="budget_limit">
                <template #label>
                  <span class="form-label">💰 预算上限</span>
                </template>
                <a-input-number
                  v-model:value="formData.budget_limit"
                  :min="100"
                  :max="100000"
                  :step="500"
                  placeholder="不填则不限预算"
                  size="large"
                  style="width: 100%"
                  addon-after="元"
                />
                <div style="color: #888; font-size: 12px; margin-top: 4px;">设置后Agent会优先推荐免票或低价景点</div>
              </a-form-item>
            </a-col>

            <!-- #11 多城市联游 -->
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">🌐 多城市联游</span>
                </template>
                <div>
                  <a-switch
                    v-model:checked="multiCityMode"
                    checked-children="已开启"
                    un-checked-children="单城市"
                    @change="onMultiCityToggle"
                    style="margin-bottom: 8px"
                  />
                  <div v-if="multiCityMode">
                    <a-select
                      v-model:value="formData.cities"
                      mode="tags"
                      :token-separators="[',', '，', '→', ' ']"
                      placeholder="输入城市后按 Enter，如：北京 → 西安 → 成都"
                      size="large"
                      style="width: 100%"
                      :open="false"
                    />
                    <div style="color: #888; font-size: 12px; margin-top: 4px;">按游览顺序输入，Agent 将生成跨城交通方案</div>
                  </div>
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 第四步:额外要求 -->
        <div class="form-section">
          <div class="section-header">
            <span class="section-icon">💬</span>
            <span class="section-title">额外要求</span>
          </div>

          <a-form-item name="free_text_input">
            <a-textarea
              v-model:value="formData.free_text_input"
              placeholder="请输入您的额外要求,例如:想去看升旗、需要无障碍设施、对海鲜过敏等..."
              :rows="3"
              size="large"
              class="custom-textarea"
            />
          </a-form-item>
        </div>

        <!-- 提交按钮 -->
        <a-form-item>
          <a-button
            type="primary"
            html-type="submit"
            :loading="loading"
            size="large"
            block
            class="submit-button"
          >
            <template v-if="!loading">
              <span class="button-icon">🚀</span>
              <span>开始规划我的旅行</span>
            </template>
            <template v-else>
              <span>正在生成中...</span>
            </template>
          </a-button>
        </a-form-item>

        <!-- 加载进度条 -->
        <a-form-item v-if="loading">
          <div class="loading-container">
            <a-progress
              :percent="loadingProgress"
              status="active"
              :stroke-color="{
                '0%': '#667eea',
                '100%': '#764ba2',
              }"
              :stroke-width="10"
            />
            <p class="loading-status">
              {{ loadingStatus }}
            </p>
          </div>
        </a-form-item>
      </a-form>
    </a-card>
  </div>

  <!-- #9 历史记录抽屉 -->
  <a-drawer
    v-model:open="historyDrawerVisible"
    title="📋 最近行程历史（最多保存10条）"
    placement="right"
    :width="400"
  >
    <div style="margin-bottom: 12px; display: flex; justify-content: flex-end;">
      <a-button danger size="small" @click="handleClearHistory">🗑️ 清空全部</a-button>
    </div>
    <div v-if="historyList.length === 0" style="text-align: center; color: #999; padding: 60px 0">
      <div style="font-size: 48px; margin-bottom: 12px">📭</div>
      暂无历史记录，规划后自动保存
    </div>
    <a-list v-else :data-source="historyList" :split="false">
      <template #renderItem="{ item }">
        <a-list-item style="padding: 0; margin-bottom: 12px">
          <a-card
            size="small"
            hoverable
            style="width: 100%; border-radius: 10px; cursor: pointer"
            @click="loadHistoryEntry(item)"
          >
            <template #title>
              <span style="font-size: 15px;">{{ item.city }} {{ item.travel_days }}日游</span>
            </template>
            <template #extra>
              <a-button type="text" danger size="small" @click.stop="handleDeleteHistory(item.id)">✕</a-button>
            </template>
            <p style="margin: 0; color: #555; font-size: 13px">📅 {{ item.start_date }} ~ {{ item.end_date }}</p>
            <p style="margin: 4px 0 0; color: #999; font-size: 12px">🕐 {{ new Date(item.created_at).toLocaleString('zh-CN') }}</p>
          </a-card>
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

// #11 多城市联游
const multiCityMode = ref(false)

// #9 历史记录
const historyDrawerVisible = ref(false)
const historyList = ref<TripHistoryEntry[]>([])

// ===== 热门城市模板 =====
const cityTemplates = [
  { city: '北京', days: 3, icon: '🏗️', desc: '故宫/长城/天坛', preferences: ['历史文化', '美食'] },
  { city: '上海', days: 2, icon: '🌆', desc: '外滩/豫园/迪士尼', preferences: ['购物', '美食', '艺术'] },
  { city: '成都', days: 3, icon: '🐼', desc: '大熊猫/宽窄巷子', preferences: ['美食', '自然风光', '休闲'] },
  { city: '杭州', days: 2, icon: '🌸', desc: '西湖/灵隐寺', preferences: ['自然风光', '历史文化', '休闲'] },
  { city: '三亚', days: 3, icon: '🏖️', desc: '亚龙湾/天涯海角', preferences: ['自然风光', '休闲'] },
  { city: '西安', days: 3, icon: '🏚️', desc: '兵马俣/回民街', preferences: ['历史文化', '美食'] },
]

const applyTemplate = (tpl: typeof cityTemplates[0]) => {
  formData.city = tpl.city
  formData.preferences = [...tpl.preferences]
  const start = dayjs().add(1, 'day')
  formData.start_date = start
  formData.end_date = start.add(tpl.days - 1, 'day')
  formData.travel_days = tpl.days
  message.success(`已应用“${tpl.city}${tpl.days}日游”模板，可根据需要修改`)
}

// ===== 日期校验 =====
const disabledStartDate = (date: Dayjs) => date.isBefore(dayjs(), 'day')
const disabledEndDate = (date: Dayjs) => {
  // 结束日期不能早于开始日期，也不能早于今天
  if (formData.start_date) {
    return date.isBefore(formData.start_date, 'day')
  }
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
  budget_limit: number | null   // #10 预算优化器
  cities: string[]              // #11 多城市联游
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

// 监听日期变化,自动计算旅行天数
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
    // 确保城市字段正确
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
      // #10 预算
      budget_limit: formData.budget_limit ?? undefined,
      // #11 多城市
      cities: (multiCityMode.value && formData.cities.length >= 2) ? formData.cities : undefined,
    }

    await generateTripPlanStream(
      requestData,
      // onProgress：使用后端真实进度替代模拟进度条 (#14)
      (evt) => {
        loadingProgress.value = evt.percent
        loadingStatus.value = evt.message
      },
      // onDone
      (plan) => {
        sessionStorage.setItem('tripPlan', JSON.stringify(plan))
        message.success('旅行计划生成成功！')
        loadingProgress.value = 100
        loadingStatus.value = '✅ 完成！'
        setTimeout(() => {
          router.push('/result')
        }, 400)
      },
      // onError
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

// ===== #11 多城市联游 =====
const onMultiCityToggle = (checked: boolean) => {
  if (!checked) {
    formData.cities = []
  } else if (formData.city) {
    formData.cities = [formData.city]
  }
}

// ===== #9 历史记录 =====
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
/* ===== 城市模板区域 ===== */
.templates-section {
  max-width: 900px;
  margin: 0 auto 24px auto;
  padding: 0 10px;
}

.templates-title {
  color: rgba(255, 255, 255, 0.9);
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  letter-spacing: 0.5px;
}

.templates-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.template-card {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 12px;
  padding: 12px 14px;
  cursor: pointer;
  transition: all 0.25s ease;
  color: white;
}

.template-card:hover {
  background: rgba(255, 255, 255, 0.28);
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
}

.tpl-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.tpl-info {
  flex: 1;
  min-width: 0;
}

.tpl-city {
  font-size: 15px;
  font-weight: 600;
}

.tpl-desc {
  font-size: 12px;
  opacity: 0.8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tpl-days {
  font-size: 13px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.2);
  padding: 2px 8px;
  border-radius: 20px;
  flex-shrink: 0;
}

.home-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 60px 20px;
  position: relative;
  overflow: hidden;
}

/* 背景装饰 */
.bg-decoration {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: hidden;
}

.circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  animation: float 20s infinite ease-in-out;
}

.circle-1 {
  width: 300px;
  height: 300px;
  top: -100px;
  left: -100px;
  animation-delay: 0s;
}

.circle-2 {
  width: 200px;
  height: 200px;
  top: 50%;
  right: -50px;
  animation-delay: 5s;
}

.circle-3 {
  width: 150px;
  height: 150px;
  bottom: -50px;
  left: 30%;
  animation-delay: 10s;
}

@keyframes float {
  0%, 100% {
    transform: translateY(0) rotate(0deg);
  }
  50% {
    transform: translateY(-30px) rotate(180deg);
  }
}

/* 页面标题 */
.page-header {
  text-align: center;
  margin-bottom: 50px;
  animation: fadeInDown 0.8s ease-out;
  position: relative;
  z-index: 1;
}

.header-actions {
  margin-top: 16px;
}

.icon-wrapper {
  margin-bottom: 20px;
}

.icon {
  font-size: 80px;
  display: inline-block;
  animation: bounce 2s infinite;
}

@keyframes bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-20px);
  }
}

.page-title {
  font-size: 56px;
  font-weight: 800;
  color: #ffffff;
  margin-bottom: 16px;
  text-shadow: 3px 3px 6px rgba(0, 0, 0, 0.3);
  letter-spacing: 2px;
}

.page-subtitle {
  font-size: 20px;
  color: rgba(255, 255, 255, 0.95);
  margin: 0;
  font-weight: 300;
}

/* 表单卡片 */
.form-card {
  max-width: 1400px;
  margin: 0 auto;
  border-radius: 24px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.4);
  animation: fadeInUp 0.8s ease-out;
  position: relative;
  z-index: 1;
  backdrop-filter: blur(10px);
  background: rgba(255, 255, 255, 0.98) !important;
}

/* 表单分区 */
.form-section {
  margin-bottom: 32px;
  padding: 24px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 16px;
  border: 1px solid #e8e8e8;
  transition: all 0.3s ease;
}

.form-section:hover {
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.15);
  transform: translateY(-2px);
}

.section-header {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 2px solid #667eea;
}

.section-icon {
  font-size: 24px;
  margin-right: 12px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

/* 表单标签 */
.form-label {
  font-size: 15px;
  font-weight: 500;
  color: #555;
}

/* 自定义输入框 */
.custom-input :deep(.ant-input),
.custom-input :deep(.ant-picker) {
  border-radius: 12px;
  border: 2px solid #e8e8e8;
  transition: all 0.3s ease;
}

.custom-input :deep(.ant-input:hover),
.custom-input :deep(.ant-picker:hover) {
  border-color: #667eea;
}

.custom-input :deep(.ant-input:focus),
.custom-input :deep(.ant-picker-focused) {
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

/* 自定义选择框 */
.custom-select :deep(.ant-select-selector) {
  border-radius: 12px !important;
  border: 2px solid #e8e8e8 !important;
  transition: all 0.3s ease;
}

.custom-select:hover :deep(.ant-select-selector) {
  border-color: #667eea !important;
}

.custom-select :deep(.ant-select-focused .ant-select-selector) {
  border-color: #667eea !important;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
}

/* 天数显示 - 紧凑版 */
.days-display-compact {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  color: white;
}

.days-display-compact .days-value {
  font-size: 24px;
  font-weight: 700;
  margin-right: 4px;
}

.days-display-compact .days-unit {
  font-size: 14px;
}

/* 偏好标签 */
.preference-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.custom-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}

.preference-tag :deep(.ant-checkbox-wrapper) {
  margin: 0 !important;
  padding: 8px 16px;
  border: 2px solid #e8e8e8;
  border-radius: 20px;
  transition: all 0.3s ease;
  background: white;
  font-size: 14px;
}

.preference-tag :deep(.ant-checkbox-wrapper:hover) {
  border-color: #667eea;
  background: #f5f7ff;
}

.preference-tag :deep(.ant-checkbox-wrapper-checked) {
  border-color: #667eea;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

/* 自定义文本域 */
.custom-textarea :deep(.ant-input) {
  border-radius: 12px;
  border: 2px solid #e8e8e8;
  transition: all 0.3s ease;
}

.custom-textarea :deep(.ant-input:hover) {
  border-color: #667eea;
}

.custom-textarea :deep(.ant-input:focus) {
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

/* 提交按钮 */
.submit-button {
  height: 56px;
  border-radius: 28px;
  font-size: 18px;
  font-weight: 600;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
  transition: all 0.3s ease;
}

.submit-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(102, 126, 234, 0.5);
}

.submit-button:active {
  transform: translateY(0);
}

.button-icon {
  margin-right: 8px;
  font-size: 20px;
}

/* 加载容器 */
.loading-container {
  text-align: center;
  padding: 24px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 16px;
  border: 2px dashed #667eea;
}

.loading-status {
  margin-top: 16px;
  color: #667eea;
  font-size: 18px;
  font-weight: 500;
}

/* 动画 */
@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>

