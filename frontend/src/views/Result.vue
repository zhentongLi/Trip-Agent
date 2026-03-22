<template>
  <div class="result-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <a-button class="back-button" size="large" @click="goBack">
        ← 返回首页
      </a-button>
      <a-space size="middle">
        <a-button v-if="!editMode" @click="toggleEditMode" type="default">
          ✏️ 编辑行程
        </a-button>
        <a-button v-else @click="saveChanges" type="primary">
          💾 保存修改
        </a-button>
        <a-button v-if="editMode" @click="cancelEdit" type="default">
          ❌ 取消编辑
        </a-button>

        <!-- 导出按钮 -->
        <a-dropdown v-if="!editMode">
          <template #overlay>
            <a-menu>
              <a-menu-item key="image" @click="exportAsImage">
                📷 导出为图片
              </a-menu-item>
              <a-menu-item key="pdf" @click="exportAsPDF">
                📄 导出为PDF
              </a-menu-item>
            </a-menu>
          </template>
          <a-button type="default">
            📥 导出行程 <DownOutlined />
          </a-button>
        </a-dropdown>

        <!-- 分享按钮 -->
        <a-button v-if="!editMode" type="default" :loading="sharing" @click="handleShare">
          🔗 分享行程
        </a-button>

        <!-- 功能27：导游RAG问答 -->
        <a-button v-if="!editMode" type="default" :loading="guiding" @click="openGuideDrawer()">
          🧭 导游问答
        </a-button>

        <!-- 功能23：保存到云端（已登录时显示） -->
        <a-button v-if="!editMode && isLoggedIn()" type="default" :loading="saving" @click="handleSaveCloud">
          ☁️ 保存云端
        </a-button>
      </a-space>
    </div>

    <div v-if="tripPlan" class="content-wrapper">
      <!-- 侧边导航 -->
      <div class="side-nav">
        <a-affix :offset-top="80">
          <a-menu mode="inline" :selected-keys="[activeSection]" @click="scrollToSection">
            <a-menu-item key="overview">
              <span>📋 行程概览</span>
            </a-menu-item>
            <a-menu-item key="budget" v-if="tripPlan.budget">
              <span>💰 预算明细</span>
            </a-menu-item>
            <a-menu-item key="map">
              <span>📍 景点地图</span>
            </a-menu-item>
            <a-sub-menu key="days" title="📅 每日行程">
              <a-menu-item v-for="(day, index) in tripPlan.days" :key="`day-${index}`">
                第{{ day.day_index + 1 }}天
              </a-menu-item>
            </a-sub-menu>
            <a-menu-item key="weather" v-if="tripPlan.weather_info && tripPlan.weather_info.length > 0">
              <span>🌤️ 天气信息</span>
            </a-menu-item>
          </a-menu>
        </a-affix>
      </div>

      <!-- 主内容区 -->
      <div class="main-content">
        <!-- 顶部信息区:左侧概览+预算,右侧地图 -->
        <div class="top-info-section">
          <!-- 左侧:行程概览和预算明细 -->
          <div class="left-info">
            <!-- 行程概览 -->
            <a-card id="overview" :title="`${tripPlan.city}旅行计划`" :bordered="false" class="overview-card">
              <div class="overview-content">
                <div class="info-item">
                  <span class="info-label">📅 日期:</span>
                  <span class="info-value">{{ tripPlan.start_date }} 至 {{ tripPlan.end_date }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">💡 建议:</span>
                  <span class="info-value">{{ tripPlan.overall_suggestions }}</span>
                </div>
              </div>
            </a-card>

            <!-- 预算明细 -->
            <a-card id="budget" v-if="tripPlan.budget" title="💰 预算明细" :bordered="false" class="budget-card">
              <div class="budget-grid">
                <div class="budget-item">
                  <div class="budget-label">景点门票</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_attractions }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">酒店住宿</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_hotels }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">餐饮费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_meals }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">交通费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_transportation }}</div>
                </div>
              </div>
              <div class="budget-total">
                <span class="total-label">预估总费用</span>
                <span class="total-value">¥{{ tripPlan.budget.total }}</span>
              </div>
            </a-card>
          </div>

          <!-- 右侧:地图 -->
          <div class="right-map">
            <a-card id="map" title="📍 景点地图" :bordered="false" class="map-card">
              <div id="amap-container" style="width: 100%; height: 600px"></div>
            </a-card>
          </div>
        </div>

        <!-- 每日行程:可折叠 -->
        <a-card title="📅 每日行程" :bordered="false" class="days-card">
          <a-collapse v-model:activeKey="activeDays" accordion>
            <a-collapse-panel
              v-for="(day, index) in tripPlan.days"
              :key="index"
              :id="`day-${index}`"
            >
              <template #header>
                <div class="day-header">
                  <span class="day-title">第{{ day.day_index + 1 }}天</span>
                  <span class="day-date">{{ day.date }}</span>
                </div>
              </template>

              <!-- 行程基本信息 -->
              <div class="day-info">
                <div class="info-row">
                  <span class="label">📝 行程描述:</span>
                  <span class="value">{{ day.description }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🚗 交通方式:</span>
                  <span class="value">{{ day.transportation }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🏨 住宿:</span>
                  <span class="value">{{ day.accommodation }}</span>
                </div>
              </div>

              <!-- 景点安排 -->
              <a-divider orientation="left">🎯 景点安排</a-divider>
              <a-list
                :data-source="day.attractions"
                :grid="{ gutter: 16, column: 2 }"
              >
                <template #renderItem="{ item, index }">
                  <a-list-item>
                    <a-card :title="item.name" size="small" class="attraction-card">
                      <!-- 编辑模式下的操作按钮 -->
                      <template #extra v-if="editMode">
                        <a-space>
                          <a-button
                            size="small"
                            @click="moveAttraction(day.day_index, index, 'up')"
                            :disabled="index === 0"
                          >
                            ↑
                          </a-button>
                          <a-button
                            size="small"
                            @click="moveAttraction(day.day_index, index, 'down')"
                            :disabled="index === day.attractions.length - 1"
                          >
                            ↓
                          </a-button>
                          <a-button
                            size="small"
                            danger
                            @click="deleteAttraction(day.day_index, index)"
                          >
                            🗑️
                          </a-button>
                        </a-space>
                      </template>

                      <!-- 景点图片 -->
                      <div class="attraction-image-wrapper">
                        <img
                          :src="getAttractionImage(item.name, index)"
                          :alt="item.name"
                          class="attraction-image"
                          @error="handleImageError"
                        />
                        <div class="attraction-badge">
                          <span class="badge-number">{{ index + 1 }}</span>
                        </div>
                        <div v-if="item.ticket_price" class="price-tag">
                          ¥{{ item.ticket_price }}
                        </div>
                      </div>

                      <!-- 编辑模式下可编辑的字段 -->
                      <div v-if="editMode">
                        <p><strong>地址:</strong></p>
                        <a-input v-model:value="item.address" size="small" style="margin-bottom: 8px" />

                        <p><strong>游览时长(分钟):</strong></p>
                        <a-input-number v-model:value="item.visit_duration" :min="10" :max="480" size="small" style="width: 100%; margin-bottom: 8px" />

                        <p><strong>描述:</strong></p>
                        <a-textarea v-model:value="item.description" :rows="2" size="small" style="margin-bottom: 8px" />
                      </div>

                      <!-- 查看模式 -->
                      <div v-else>
                        <p><strong>地址:</strong> {{ item.address }}</p>
                        <p><strong>游览时长:</strong> {{ item.visit_duration }}分钟</p>
                        <p v-if="item.opening_hours"><strong>⏰ 开放时间:</strong> {{ item.opening_hours }}</p>
                        <p><strong>描述:</strong> {{ item.description }}</p>
                        <p v-if="item.rating"><strong>评分:</strong> {{ item.rating }}⭐</p>
                        <a-button type="link" size="small" style="padding-left: 0" @click="openGuideDrawer(item.name)">
                          🎙️ 获取导游解说
                        </a-button>
                      </div>
                    </a-card>
                  </a-list-item>
                </template>
              </a-list>

              <!-- 酒店推荐 -->
              <a-divider v-if="day.hotel" orientation="left">🏨 住宿推荐</a-divider>
              <a-card v-if="day.hotel" size="small" class="hotel-card">
                <template #title>
                  <span class="hotel-title">{{ day.hotel.name }}</span>
                </template>
                <a-descriptions :column="2" size="small">
                  <a-descriptions-item label="地址">{{ day.hotel.address }}</a-descriptions-item>
                  <a-descriptions-item label="类型">{{ day.hotel.type }}</a-descriptions-item>
                  <a-descriptions-item label="价格范围">{{ day.hotel.price_range }}</a-descriptions-item>
                  <a-descriptions-item label="评分">{{ day.hotel.rating }}⭐</a-descriptions-item>
                  <a-descriptions-item label="距离" :span="2">{{ day.hotel.distance }}</a-descriptions-item>
                </a-descriptions>
              </a-card>

              <!-- 餐饮安排 -->
              <a-divider orientation="left">🍽️ 餐饮安排</a-divider>
              <a-descriptions :column="1" bordered size="small">
                <a-descriptions-item
                  v-for="meal in day.meals"
                  :key="meal.type"
                  :label="getMealLabel(meal.type)"
                >
                  {{ meal.name }}
                  <span v-if="meal.description"> - {{ meal.description }}</span>
                </a-descriptions-item>
              </a-descriptions>
            </a-collapse-panel>
          </a-collapse>
        </a-card>

        <a-card id="weather" v-if="tripPlan.weather_info && tripPlan.weather_info.length > 0" title="天气信息" style="margin-top: 20px" :bordered="false">
        <a-list
          :data-source="tripPlan.weather_info"
          :grid="{ gutter: 16, column: 3 }"
        >
          <template #renderItem="{ item }">
            <a-list-item>
              <a-card size="small" class="weather-card">
                <div class="weather-date">{{ item.date }}</div>
                <div class="weather-info-row">
                  <span class="weather-icon">☀️</span>
                  <div>
                    <div class="weather-label">白天</div>
                    <div class="weather-value">{{ item.day_weather }} {{ item.day_temp }}°C</div>
                  </div>
                </div>
                <div class="weather-info-row">
                  <span class="weather-icon">🌙</span>
                  <div>
                    <div class="weather-label">夜间</div>
                    <div class="weather-value">{{ item.night_weather }} {{ item.night_temp }}°C</div>
                  </div>
                </div>
                <div class="weather-wind">
                  💨 {{ item.wind_direction }} {{ item.wind_power }}
                </div>
                <!-- #13 天气预警标签 -->
                <div v-if="item.weather_warning" class="weather-warning-tag">
                  🚨 {{ item.weather_warning }}
                </div>
              </a-card>
            </a-list-item>
          </template>
        </a-list>
        </a-card>
      </div>
    </div>

    <a-empty v-else description="没有找到旅行计划数据">
      <template #image>
        <div style="font-size: 80px;">🗺️</div>
      </template>
      <template #description>
        <span style="color: #999;">暂无旅行计划数据,请先创建行程</span>
      </template>
      <a-button type="primary" @click="goBack">返回首页创建行程</a-button>
    </a-empty>

    <!-- 回到顶部按钮 -->
    <a-back-top :visibility-height="300">
      <div class="back-top-button">
        ↑
      </div>
    </a-back-top>

    <!-- 功能20：AI 行程调整 浮动按钮 -->
    <div v-if="tripPlan" class="ai-chat-fab" @click="showAdjustDrawer = true" title="AI 调整行程">
      🤖
    </div>

    <!-- 功能27：导游RAG模式 浮动按钮 -->
    <div v-if="tripPlan" class="guide-chat-fab" @click="openGuideDrawer()" title="导游RAG问答">
      🧭
    </div>

    <!-- AI 调整抽屉 -->
    <a-drawer
      v-model:open="showAdjustDrawer"
      title="🤖 AI 行程调整"
      placement="right"
      :width="420"
    >
      <div class="adjust-drawer-content">
        <!-- 对话历史 -->
        <div class="chat-history" ref="chatHistoryRef">
          <div v-if="chatMessages.length === 0" class="chat-empty">
            <p>💡 用自然语言描述你想改什么，例如：</p>
            <div class="chat-examples">
              <a-tag color="blue" style="cursor:pointer;margin-bottom:8px"
                @click="fillExample('把第二天的第一个景点换成大猫山景区')">
                📌 把第二天第一个景点换成大猫山景区
              </a-tag>
              <a-tag color="green" style="cursor:pointer;margin-bottom:8px"
                @click="fillExample('第三天加一个晚上看头显演出的地方')">
                🎬 第三天加晚上看演出的地方
              </a-tag>
              <a-tag color="purple" style="cursor:pointer;margin-bottom:8px"
                @click="fillExample('把每天的早餐改成袋粥/稀饭类小吃')">
                🍚 每天早餐改成稀饭类小吃
              </a-tag>
              <a-tag color="orange" style="cursor:pointer;margin-bottom:8px"
                @click="fillExample('把住宿改成民宿风格')">
                🏡 把住宿改成民宿风格
              </a-tag>
            </div>
          </div>
          <div
            v-for="(msg, idx) in chatMessages"
            :key="idx"
            :class="['chat-bubble', msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai']"
          >
            <div class="bubble-meta">
              <span class="bubble-role">{{ msg.role === 'user' ? '👤 我' : '🤖 AI' }}</span>
              <span class="bubble-time">{{ msg.timestamp }}</span>
            </div>
            <div class="bubble-content">{{ msg.content }}</div>
          </div>
          <div v-if="adjusting" class="chat-bubble chat-bubble-ai">
            <div class="bubble-meta"><span class="bubble-role">🤖 AI</span></div>
            <div class="bubble-content"><a-spin size="small" /> 正在调整行程，稍等...</div>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="chat-input-area">
          <a-textarea
            v-model:value="adjustInput"
            placeholder="描述你想如何修改行程... (Ctrl+Enter 发送)"
            :rows="3"
            :maxlength="500"
            show-count
            :disabled="adjusting"
            @keydown.ctrl.enter="handleAdjust"
          />
          <div class="chat-input-actions">
            <a-button type="primary" :loading="adjusting" @click="handleAdjust" block>
              🚀 发送 (Ctrl+Enter)
            </a-button>
            <a-button
              size="small" @click="chatMessages = []" style="margin-top:8px" block
              :disabled="chatMessages.length === 0"
            >
              🗑️ 清空对话记录
            </a-button>
          </div>
        </div>
      </div>
    </a-drawer>

    <!-- 功能27：导游RAG抽屉 -->
    <a-drawer
      v-model:open="showGuideDrawer"
      title="🧭 导游RAG模式"
      placement="right"
      :width="460"
    >
      <div class="adjust-drawer-content">
        <div v-if="isDevEnv" class="guide-debug-toggle">
          <a-space size="small" wrap>
            <a-switch v-model:checked="guideDebugEnabled" size="small" />
            <span class="guide-debug-toggle-text">调试模式（显示 Skill/RAG 命中详情）</span>
            <a-tag color="processing">会话: {{ shortGuideSessionId(guideSessionId) }}</a-tag>
          </a-space>
        </div>
        <div class="guide-context" v-if="guideAttractionName">
          当前景点上下文：<a-tag color="blue">{{ guideAttractionName }}</a-tag>
        </div>
        <div class="chat-history" ref="guideHistoryRef">
          <div v-if="guideMessages.length === 0" class="chat-empty">
            <p>💡 可提问示例：</p>
            <div class="chat-examples">
              <a-tag color="blue" style="cursor:pointer;margin-bottom:8px"
                @click="fillGuideExample('这个行程里最值得早起去的景点是哪个？为什么？')">
                🌅 哪个景点最适合早去？
              </a-tag>
              <a-tag color="green" style="cursor:pointer;margin-bottom:8px"
                @click="fillGuideExample('请给我一份今天的游览顺序和避坑建议')">
                🗺️ 今日游览顺序+避坑建议
              </a-tag>
              <a-tag color="orange" style="cursor:pointer;margin-bottom:8px"
                @click="fillGuideExample('预算有限，哪些景点可以缩短停留时间？')">
                💰 预算有限如何优化时间？
              </a-tag>
            </div>
          </div>

          <div
            v-for="(msg, idx) in guideMessages"
            :key="`guide-${idx}`"
            :class="['chat-bubble', msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai']"
          >
            <div class="bubble-meta">
              <span class="bubble-role">{{ msg.role === 'user' ? '👤 我' : '🧭 导游AI' }}</span>
              <span class="bubble-time">{{ msg.timestamp }}</span>
            </div>
            <div class="bubble-content">{{ msg.content }}</div>
            <div v-if="msg.references && msg.references.length > 0" class="guide-refs">
              <div class="guide-refs-title">参考资料</div>
              <a-space wrap>
                <a-tag v-for="(reference, rIdx) in msg.references" :key="rIdx" color="geekblue">
                  {{ reference.title }}
                </a-tag>
              </a-space>
            </div>

            <div v-if="isDevEnv && msg.debugMeta" class="guide-debug-panel">
              <div class="guide-debug-title">🧪 调试面板</div>
              <a-space wrap size="small" class="guide-debug-tags">
                <a-tag color="purple">
                  Skill: {{ msg.debugMeta.skill_meta?.skill_name || '-' }}
                </a-tag>
                <a-tag :color="msg.debugMeta.retrieval_meta?.has_local_kb_hit ? 'success' : 'error'">
                  本地知识库命中: {{ msg.debugMeta.retrieval_meta?.has_local_kb_hit ? '是' : '否' }}
                </a-tag>
                <a-tag :color="msg.debugMeta.retrieval_meta?.vector_store_enabled ? 'blue' : 'default'">
                  向量库: {{ msg.debugMeta.retrieval_meta?.vector_store_enabled ? '启用' : '关闭' }}
                </a-tag>
                <a-tag color="geekblue">
                  重排: {{ msg.debugMeta.retrieval_meta?.reranker_mode || '-' }}
                </a-tag>
                <a-tag color="cyan">
                  迭代轮次: {{ msg.debugMeta.retrieval_meta?.iterative_rounds ?? 0 }}
                </a-tag>
              </a-space>

              <div
                v-if="sourceCountEntries(msg.debugMeta.retrieval_meta?.source_counts).length > 0"
                class="guide-debug-block"
              >
                <div class="guide-debug-label">来源统计</div>
                <a-space wrap size="small">
                  <a-tag
                    v-for="([source, count], sIdx) in sourceCountEntries(msg.debugMeta.retrieval_meta?.source_counts)"
                    :key="`source-${idx}-${sIdx}`"
                    color="blue"
                  >
                    {{ formatSourceLabel(source) }}: {{ count }}
                  </a-tag>
                </a-space>
              </div>

              <div
                v-if="msg.debugMeta.retrieval_meta?.rewritten_queries && msg.debugMeta.retrieval_meta.rewritten_queries.length > 0"
                class="guide-debug-block"
              >
                <div class="guide-debug-label">改写查询</div>
                <ol class="guide-debug-query-list">
                  <li
                    v-for="(query, qIdx) in msg.debugMeta.retrieval_meta?.rewritten_queries"
                    :key="`query-${idx}-${qIdx}`"
                  >
                    {{ query }}
                  </li>
                </ol>
              </div>
            </div>
          </div>

          <div v-if="guiding" class="chat-bubble chat-bubble-ai">
            <div class="bubble-meta"><span class="bubble-role">🧭 导游AI</span></div>
            <div class="bubble-content"><a-spin size="small" /> 正在检索资料并生成解说，请稍等...</div>
          </div>
        </div>

        <div class="chat-input-area">
          <a-textarea
            v-model:value="guideInput"
            placeholder="例如：这个景点的最佳游览时段和拍照位是什么？(Ctrl+Enter 发送)"
            :rows="3"
            :maxlength="500"
            show-count
            :disabled="guiding"
            @keydown.ctrl.enter="handleGuideAsk"
          />
          <div class="chat-input-actions">
            <a-button type="primary" :loading="guiding" @click="handleGuideAsk" block>
              🎙️ 发送提问 (Ctrl+Enter)
            </a-button>
            <a-button
              size="small"
              style="margin-top:8px"
              @click="guideMessages = []"
              :disabled="guideMessages.length === 0"
              block
            >
              🗑️ 清空导游对话
            </a-button>
          </div>
        </div>
      </div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownOutlined } from '@ant-design/icons-vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import html2canvas from 'html2canvas'
import type { TripPlan, AdjustChatEntry, GuideReference, GuideDebugMeta } from '@/types'
import { createShare, getSharedTrip, saveHistory, adjustTripPlan, exportTripPdfBackend, saveUserTrip, askGuideQuestion } from '@/services/api'
import { isLoggedIn, getToken } from '@/services/auth'

const router = useRouter()
const route = useRoute()
const tripPlan = ref<TripPlan | null>(null)
const editMode = ref(false)
const originalPlan = ref<TripPlan | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const activeSection = ref('overview')
const activeDays = ref<number[]>([0]) // 默认展开第一天
const sharing = ref(false)
// 功能23：云端保存
const saving = ref(false)
// 功能20：AI 行程调整
const showAdjustDrawer = ref(false)
const adjustInput = ref('')
const adjusting = ref(false)
const chatMessages = ref<AdjustChatEntry[]>([])
const chatHistoryRef = ref<HTMLDivElement | null>(null)
// 功能27：导游RAG问答
type GuideChatEntry = {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  references?: GuideReference[]
  debugMeta?: GuideDebugMeta
}
const showGuideDrawer = ref(false)
const guideInput = ref('')
const guiding = ref(false)
const guideAttractionName = ref('')
const guideMessages = ref<GuideChatEntry[]>([])
const guideHistoryRef = ref<HTMLDivElement | null>(null)
const isDevEnv = import.meta.env.DEV
const guideDebugEnabled = ref(false)
const GUIDE_SESSION_KEY = 'guide_session_id'
const getOrCreateGuideSessionId = (): string => {
  const existing = sessionStorage.getItem(GUIDE_SESSION_KEY)
  if (existing) return existing
  const sid = `guide-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
  sessionStorage.setItem(GUIDE_SESSION_KEY, sid)
  return sid
}
const guideSessionId = ref('')
let map: any = null

const loadPlanData = async () => {
  // 优先从 URL 参数加载分享行程
  const shareId = route.query.share as string
  if (shareId) {
    try {
      message.loading({ content: '正在加载分享行程...', key: 'share-load', duration: 0 })
      const resp = await getSharedTrip(shareId)
      if (resp.success && resp.data) {
        tripPlan.value = resp.data
        message.success({ content: '分享行程加载成功！', key: 'share-load' })
      }
    } catch (e: any) {
      message.error({ content: `加载分享行程失败: ${e.message}`, key: 'share-load' })
    }
  } else {
    // 从 sessionStorage 加载
    const data = sessionStorage.getItem('tripPlan')
    if (data) {
      tripPlan.value = JSON.parse(data)
      // #9 保存到历史记录
      if (tripPlan.value) {
        try { saveHistory(tripPlan.value) } catch {}
      }
    }
  }

  attractionPhotos.value = {}
  if (map) {
    map.destroy()
    map = null
  }

  if (tripPlan.value) {
    await loadAttractionPhotos()
    await nextTick()
    await initMap()
  }
}

const handleTripPlanUpdated = async () => {
  await loadPlanData()
}

onMounted(async () => {
  guideSessionId.value = getOrCreateGuideSessionId()
  window.addEventListener('trip-plan-updated', handleTripPlanUpdated)
  await loadPlanData()
})

onBeforeUnmount(() => {
  window.removeEventListener('trip-plan-updated', handleTripPlanUpdated)
})

watch(
  () => route.fullPath,
  async (newPath, oldPath) => {
    if (newPath !== oldPath) {
      await loadPlanData()
    }
  }
)

// 分享行程
const handleShare = async () => {
  if (!tripPlan.value) return
  sharing.value = true
  try {
    const result = await createShare(tripPlan.value, `${tripPlan.value.city} ${tripPlan.value.start_date} 行程`)
    const shareUrl = result.share_url.startsWith('http')
      ? result.share_url
      : `${window.location.origin}${result.share_url.startsWith('/') ? '' : '/'}${result.share_url}`
    await navigator.clipboard.writeText(shareUrl)
    message.success({
      content: `🔗 分享链接已复制！ID: ${result.share_id}（7天内有效）`,
      duration: 5
    })
  } catch (e: any) {
    message.error(`分享失败: ${e.message}`)
  } finally {
    sharing.value = false
  }
}

// 功能23：云端保存（已登录时可用）
const handleSaveCloud = async () => {
  if (!tripPlan.value) return
  const token = getToken()
  if (!token) return
  saving.value = true
  try {
    const title = `${tripPlan.value.city} ${tripPlan.value.start_date} 行程`
    await saveUserTrip(tripPlan.value, token, title)
    message.success('☁️ 行程已保存到云端！')
  } catch (e: any) {
    message.error(`保存失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    saving.value = false
  }
}

// 功能20：AI 行程调整
const fillExample = (text: string) => {
  adjustInput.value = text
}

const scrollChatToBottom = async () => {
  await nextTick()
  if (chatHistoryRef.value) {
    chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight
  }
}

const fillGuideExample = (text: string) => {
  guideInput.value = text
}

const shortGuideSessionId = (sid: string): string => {
  if (!sid) return '-'
  if (sid.length <= 16) return sid
  return `${sid.slice(0, 8)}...${sid.slice(-4)}`
}

const sourceCountEntries = (counts?: Record<string, number>): Array<[string, number]> => {
  if (!counts) return []
  return Object.entries(counts)
}

const formatSourceLabel = (source: string): string => {
  const map: Record<string, string> = {
    knowledge_base: '本地知识库',
    trip_plan: '当前行程',
  }
  return map[source] || source
}

const scrollGuideToBottom = async () => {
  await nextTick()
  if (guideHistoryRef.value) {
    guideHistoryRef.value.scrollTop = guideHistoryRef.value.scrollHeight
  }
}

const openGuideDrawer = (attractionName?: string) => {
  showGuideDrawer.value = true
  if (attractionName) {
    guideAttractionName.value = attractionName
    guideInput.value = `请介绍${tripPlan.value?.city || ''}${attractionName}的亮点、最佳游览时段和避坑建议。`
  }
}

const handleGuideAsk = async () => {
  const q = guideInput.value.trim()
  if (!q || !tripPlan.value) return
  if (guiding.value) return

  const timestamp = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  guideMessages.value.push({ role: 'user', content: q, timestamp })
  guideInput.value = ''
  guiding.value = true
  await scrollGuideToBottom()

  try {
    const result = await askGuideQuestion({
      question: q,
      session_id: guideSessionId.value || getOrCreateGuideSessionId(),
      debug: isDevEnv && guideDebugEnabled.value,
      city: tripPlan.value.city,
      attraction_name: guideAttractionName.value || undefined,
      trip_plan: tripPlan.value,
      top_k: 4,
    })

    guideMessages.value.push({
      role: 'assistant',
      content: result.answer,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      references: result.references,
      debugMeta: result.debug_meta || undefined,
    })
  } catch (e: any) {
    guideMessages.value.push({
      role: 'assistant',
      content: `抱歉，导游问答失败：${e.response?.data?.detail || e.message}`,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    })
    message.error(`导游问答失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    guiding.value = false
    await scrollGuideToBottom()
  }
}

const handleAdjust = async () => {
  const msg = adjustInput.value.trim()
  if (!msg || !tripPlan.value) return
  if (adjusting.value) return

  // 添加用户消息
  const timestamp = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  chatMessages.value.push({ role: 'user', content: msg, timestamp })
  adjustInput.value = ''
  adjusting.value = true
  await scrollChatToBottom()

  try {
    const newPlan = await adjustTripPlan(tripPlan.value, msg)
    tripPlan.value = newPlan
    sessionStorage.setItem('tripPlan', JSON.stringify(newPlan))

    // 重新渲染地图
    if (map) { map.destroy(); map = null }
    await nextTick()
    initMap()

    chatMessages.value.push({
      role: 'assistant',
      content: `✅ 行程已根据您的要求调整完成！如果调整结果不理想可以继续提出修改要求。`,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    })
    message.success('行程已更新！')
  } catch (e: any) {
    chatMessages.value.push({
      role: 'assistant',
      content: `❌ 调整失败：${e.message}。请重试或控制该要求描述得更具体。`,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    })
    message.error(`AI 调整失败: ${e.message}`)
  } finally {
    adjusting.value = false
    await scrollChatToBottom()
  }
}

const goBack = () => {
  router.push('/')
}

// 滚动到指定区域
const scrollToSection = ({ key }: { key: string }) => {
  activeSection.value = key
  const element = document.getElementById(key)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

// 切换编辑模式
const toggleEditMode = () => {
  editMode.value = true
  // 保存原始数据用于取消编辑
  originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))
  message.info('进入编辑模式')
}

// 保存修改
const saveChanges = () => {
  editMode.value = false
  // 更新sessionStorage
  if (tripPlan.value) {
    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan.value))
  }
  message.success('修改已保存')

  // 重新初始化地图以反映更改
  if (map) {
    map.destroy()
  }
  nextTick(() => {
    initMap()
  })
}

// 取消编辑
const cancelEdit = () => {
  if (originalPlan.value) {
    tripPlan.value = JSON.parse(JSON.stringify(originalPlan.value))
  }
  editMode.value = false
  message.info('已取消编辑')
}

// 删除景点
const deleteAttraction = (dayIndex: number, attrIndex: number) => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  if (day.attractions.length <= 1) {
    message.warning('每天至少需要保留一个景点')
    return
  }

  day.attractions.splice(attrIndex, 1)
  message.success('景点已删除')
}

// 移动景点顺序
const moveAttraction = (dayIndex: number, attrIndex: number, direction: 'up' | 'down') => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  const attractions = day.attractions

  if (direction === 'up' && attrIndex > 0) {
    [attractions[attrIndex], attractions[attrIndex - 1]] = [attractions[attrIndex - 1], attractions[attrIndex]]
  } else if (direction === 'down' && attrIndex < attractions.length - 1) {
    [attractions[attrIndex], attractions[attrIndex + 1]] = [attractions[attrIndex + 1], attractions[attrIndex]]
  }
}

const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = {
    breakfast: '早餐',
    lunch: '午餐',
    dinner: '晚餐',
    snack: '小吃'
  }
  return labels[type] || type
}

// 加载所有景点图片
const loadAttractionPhotos = async () => {
  if (!tripPlan.value) return

  const promises: Promise<void>[] = []
  const city = tripPlan.value.city ?? ''

  tripPlan.value.days.forEach(day => {
    day.attractions.forEach(attraction => {
      const promise = fetch(`http://localhost:8000/api/poi/photo?name=${encodeURIComponent(attraction.name)}&city=${encodeURIComponent(city)}`)
        .then(res => res.json())
        .then(data => {
          if (data.success && data.data.photo_url) {
            attractionPhotos.value[attraction.name] = data.data.photo_url
          }
        })
        .catch(err => {
          console.error(`获取${attraction.name}图片失败:`, err)
        })

      promises.push(promise)
    })
  })

  await Promise.all(promises)
}

// 获取景点图片
const getAttractionImage = (name: string, index: number): string => {
  // 如果已加载真实图片,返回真实图片
  if (attractionPhotos.value[name]) {
    return attractionPhotos.value[name]
  }

  // 返回一个纯色占位图(避免跨域问题)
  const colors = [
    { start: '#667eea', end: '#764ba2' },
    { start: '#f093fb', end: '#f5576c' },
    { start: '#4facfe', end: '#00f2fe' },
    { start: '#43e97b', end: '#38f9d7' },
    { start: '#fa709a', end: '#fee140' }
  ]
  const colorIndex = index % colors.length
  const { start, end } = colors[colorIndex]

  // 使用base64编码避免中文问题
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
    <defs>
      <linearGradient id="grad${index}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:${start};stop-opacity:1" />
        <stop offset="100%" style="stop-color:${end};stop-opacity:1" />
      </linearGradient>
    </defs>
    <rect width="400" height="300" fill="url(#grad${index})"/>
    <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="24" font-weight="bold" fill="white">${name}</text>
  </svg>`

  return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
}

// 图片加载失败时的处理
const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  // 使用灰色占位图
  img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="300"%3E%3Crect width="400" height="300" fill="%23f0f0f0"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="%23999"%3E图片加载失败%3C/text%3E%3C/svg%3E'
}



// 导出为图片
const exportAsImage = async () => {
  try {
    message.loading({ content: '正在生成图片...', key: 'export', duration: 0 })

    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) {
      throw new Error('未找到内容元素')
    }

    // 创建一个独立的容器
    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5f7fa'
    exportContainer.style.padding = '20px'

    // 复制所有内容
    exportContainer.innerHTML = element.innerHTML

    // 处理地图截图
    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }

    // 移除所有ant-card类,替换为纯div
    const cards = exportContainer.querySelectorAll('.ant-card')
    cards.forEach((card) => {
      const cardEl = card as HTMLElement
      try {
        cardEl.className = '' // 移除所有类
        cardEl.style.setProperty('background-color', '#ffffff')
        cardEl.style.setProperty('border-radius', '12px')
        cardEl.style.setProperty('box-shadow', '0 4px 12px rgba(0, 0, 0, 0.1)')
        cardEl.style.setProperty('margin-bottom', '20px')
        cardEl.style.setProperty('overflow', 'hidden')
      } catch (err) {
        console.error('设置卡片样式失败:', err)
      }
    })

    // 处理卡片头部
    const cardHeads = exportContainer.querySelectorAll('.ant-card-head')
    cardHeads.forEach((head) => {
      const headEl = head as HTMLElement
      try {
        headEl.style.setProperty('background-color', '#667eea')
        headEl.style.setProperty('color', '#ffffff')
        headEl.style.setProperty('padding', '16px 24px')
        headEl.style.setProperty('font-size', '18px')
        headEl.style.setProperty('font-weight', '600')
      } catch (err) {
        console.error('设置卡片头部样式失败:', err)
      }
    })

    // 处理卡片内容
    const cardBodies = exportContainer.querySelectorAll('.ant-card-body')
    cardBodies.forEach((body) => {
      const bodyEl = body as HTMLElement
      bodyEl.style.setProperty('background-color', '#ffffff')
      bodyEl.style.setProperty('padding', '24px')
    })

    // 处理酒店卡片头部
    const hotelCards = exportContainer.querySelectorAll('.hotel-card')
    hotelCards.forEach((card) => {
      const head = card.querySelector('.ant-card-head') as HTMLElement
      if (head) {
        head.style.setProperty('background-color', '#1976d2')
      }
      (card as HTMLElement).style.setProperty('background-color', '#e3f2fd')
    })

    // 处理天气卡片
    const weatherCards = exportContainer.querySelectorAll('.weather-card')
    weatherCards.forEach((card) => {
      (card as HTMLElement).style.setProperty('background-color', '#e0f7fa')
    })

    // 处理预算总计
    const budgetTotal = exportContainer.querySelector('.budget-total')
    if (budgetTotal) {
      const el = budgetTotal as HTMLElement
      el.style.setProperty('background-color', '#667eea')
      el.style.setProperty('color', '#ffffff')
      el.style.setProperty('padding', '20px')
      el.style.setProperty('border-radius', '12px')
      el.style.setProperty('margin-bottom', '20px')
    }

    // 处理预算项
    const budgetItems = exportContainer.querySelectorAll('.budget-item')
    budgetItems.forEach((item) => {
      const el = item as HTMLElement
      el.style.setProperty('background-color', '#f5f7fa')
      el.style.setProperty('padding', '16px')
      el.style.setProperty('border-radius', '8px')
      el.style.setProperty('margin-bottom', '12px')
    })

    // 添加到body(隐藏)
    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)

    const canvas = await html2canvas(exportContainer, {
      backgroundColor: '#f5f7fa',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true
    })

    // 移除容器
    document.body.removeChild(exportContainer)

    // 转换为图片并下载
    const link = document.createElement('a')
    link.download = `旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()

    message.success({ content: '图片导出成功!', key: 'export' })
  } catch (error: any) {
    console.error('导出图片失败:', error)
    message.error({ content: `导出图片失败: ${error.message}`, key: 'export' })
  }
}

// 功能22：导出为 PDF（后端 ReportLab，取代前端 html2canvas 方案）
const exportAsPDF = async () => {
  if (!tripPlan.value) return
  try {
    message.loading({ content: '正在生成 PDF，请稍候...', key: 'export', duration: 0 })
    await exportTripPdfBackend(tripPlan.value)
    message.success({ content: '📄 PDF 导出成功，正在下载！', key: 'export', duration: 3 })
  } catch (error: any) {
    console.error('导出 PDF 失败:', error)
    message.error({ content: `导出 PDF 失败: ${error.message}`, key: 'export' })
  }
}

// 初始化地图
const initMap = async () => {
  try {
    // _AMapSecurityConfig 已在 main.ts 顶部全局注入，此处无需重复设置
    const AMap = await AMapLoader.load({
      key: import.meta.env.VITE_AMAP_WEB_JS_KEY,
      version: '2.0',
      plugins: ['AMap.Marker', 'AMap.Polyline', 'AMap.InfoWindow']
    })

    // 创建地图实例
    map = new AMap.Map('amap-container', {
      zoom: 12,
      viewMode: '3D'
    })

    // 设置地图中心到实际目的地城市（自动地理编码）
    if (tripPlan.value?.city) {
      map.setCity(tripPlan.value.city)
    }

    // 添加景点标记
    addAttractionMarkers(AMap)

    message.success('地图加载成功')
  } catch (error) {
    console.error('地图加载失败:', error)
    message.error('地图加载失败')
  }
}

// 添加景点标记
const addAttractionMarkers = (AMap: any) => {
  if (!tripPlan.value) return

  const markers: any[] = []
  const allAttractions: any[] = []

  // 收集所有景点
  tripPlan.value.days.forEach((day, dayIndex) => {
    day.attractions.forEach((attraction, attrIndex) => {
      if (attraction.location && attraction.location.longitude && attraction.location.latitude) {
        allAttractions.push({
          ...attraction,
          dayIndex,
          attrIndex
        })
      }
    })
  })

  // 创建标记
  allAttractions.forEach((attraction, index) => {
    const marker = new AMap.Marker({
      position: [attraction.location.longitude, attraction.location.latitude],
      title: attraction.name,
      label: {
        content: `<div style="background: #4CAF50; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">${index + 1}</div>`,
        offset: new AMap.Pixel(0, -30)
      }
    })

    // 创建信息窗口
    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding: 10px;">
          <h4 style="margin: 0 0 8px 0;">${attraction.name}</h4>
          <p style="margin: 4px 0;"><strong>地址:</strong> ${attraction.address}</p>
          <p style="margin: 4px 0;"><strong>游览时长:</strong> ${attraction.visit_duration}分钟</p>
          <p style="margin: 4px 0;"><strong>描述:</strong> ${attraction.description}</p>
          <p style="margin: 4px 0; color: #1890ff;"><strong>第${attraction.dayIndex + 1}天 景点${attraction.attrIndex + 1}</strong></p>
        </div>
      `,
      offset: new AMap.Pixel(0, -30)
    })

    // 点击标记显示信息窗口
    marker.on('click', () => {
      infoWindow.open(map, marker.getPosition())
    })

    markers.push(marker)
  })

  // 添加标记到地图
  map.add(markers)

  // 自动调整视野以包含所有标记
  if (allAttractions.length > 0) {
    map.setFitView(markers)
  }

  // 绘制路线
  drawRoutes(AMap, allAttractions)
}

// 绘制路线
const drawRoutes = (AMap: any, attractions: any[]) => {
  if (attractions.length < 2) return

  // 按天分组绘制路线
  const dayGroups: any = {}
  attractions.forEach(attr => {
    if (!dayGroups[attr.dayIndex]) {
      dayGroups[attr.dayIndex] = []
    }
    dayGroups[attr.dayIndex].push(attr)
  })

  // 为每天的景点绘制路线
  Object.values(dayGroups).forEach((dayAttractions: any) => {
    if (dayAttractions.length < 2) return

    const path = dayAttractions.map((attr: any) => [
      attr.location.longitude,
      attr.location.latitude
    ])

    const polyline = new AMap.Polyline({
      path: path,
      strokeColor: '#1890ff',
      strokeWeight: 4,
      strokeOpacity: 0.8,
      strokeStyle: 'solid',
      showDir: true // 显示方向箭头
    })

    map.add(polyline)
  })
}
</script>

<style scoped>
.result-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  padding: 40px 20px;
}

.page-header {
  max-width: 1200px;
  margin: 0 auto 30px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  animation: fadeInDown 0.6s ease-out;
}

.back-button {
  border-radius: 8px;
  font-weight: 500;
}

/* 内容布局 */
.content-wrapper {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  gap: 24px;
}

.side-nav {
  width: 240px;
  flex-shrink: 0;
}

.side-nav :deep(.ant-menu) {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  background: white;
}

.side-nav :deep(.ant-menu-item) {
  margin: 4px 8px;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.side-nav :deep(.ant-menu-item-selected) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.side-nav :deep(.ant-menu-item:hover) {
  background: rgba(102, 126, 234, 0.1);
}

.main-content {
  flex: 1;
  min-width: 0;
}

/* 景点图片样式 */
.attraction-image-wrapper {
  position: relative;
  margin-bottom: 12px;
  border-radius: 8px;
  overflow: hidden;
}

.attraction-image {
  width: 100%;
  height: 200px;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.attraction-image-wrapper:hover .attraction-image {
  transform: scale(1.05);
}

.attraction-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.badge-number {
  font-size: 18px;
}

.price-tag {
  position: absolute;
  top: 12px;
  right: 12px;
  background: rgba(255, 77, 79, 0.9);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-weight: bold;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

/* 天气卡片样式 */
.weather-card {
  background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 100%);
  border: none !important;
  transition: all 0.3s ease;
}

.weather-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
}

.weather-date {
  font-size: 16px;
  font-weight: bold;
  color: #00796b;
  margin-bottom: 12px;
  text-align: center;
}

.weather-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.weather-icon {
  font-size: 24px;
}

.weather-label {
  font-size: 12px;
  color: #666;
}

.weather-value {
  font-size: 16px;
  font-weight: 600;
  color: #00796b;
}

.weather-wind {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(0, 121, 107, 0.2);
  text-align: center;
  color: #00796b;
  font-size: 14px;
}

/* #13 天气预警标签 */
.weather-warning-tag {
  margin-top: 8px;
  padding: 4px 8px;
  background: #fff1f0;
  border: 1px solid #ffa39e;
  border-radius: 6px;
  color: #cf1322;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  animation: pulse-warning 2s infinite;
}

@keyframes pulse-warning {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* 回到顶部按钮 */
.back-top-button {
  width: 50px;
  height: 50px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  transition: all 0.3s ease;
}

.back-top-button:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}

/* 酒店卡片样式 */
.hotel-card {
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border: none !important;
}

.hotel-card :deep(.ant-card-head) {
  background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
}

.hotel-title {
  color: white !important;
  font-weight: 600;
}

/* 顶部信息区布局 */
.top-info-section {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}

.left-info {
  flex: 0 0 400px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.right-map {
  flex: 1;
}

/* 行程概览卡片 */
.overview-card {
  height: fit-content;
}

.overview-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 14px;
  font-weight: 600;
  color: #666;
}

.info-value {
  font-size: 15px;
  color: #333;
  line-height: 1.6;
}

/* 预算卡片 */
.budget-card {
  height: fit-content;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.budget-item {
  text-align: center;
  padding: 12px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.budget-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.budget-value {
  font-size: 20px;
  font-weight: 700;
  color: #1890ff;
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  color: white;
}

.total-label {
  font-size: 16px;
  font-weight: 600;
}

.total-value {
  font-size: 28px;
  font-weight: 700;
}

/* 地图卡片 */
.map-card {
  height: 100%;
}

.map-card :deep(.ant-card-body) {
  padding: 0;
}

/* 每日行程卡片 */
.days-card {
  margin-top: 20px;
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.day-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.day-date {
  font-size: 14px;
  color: #999;
}

.day-info {
  margin-bottom: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.info-row {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-row .label {
  font-weight: 600;
  color: #666;
  min-width: 100px;
}

.info-row .value {
  color: #333;
  flex: 1;
}

/* 卡片样式优化 */
:deep(.ant-card) {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  margin-bottom: 20px;
  transition: all 0.3s ease;
  animation: fadeInUp 0.6s ease-out;
}

:deep(.ant-card:hover) {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

:deep(.ant-card-head) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white !important;
  border-radius: 12px 12px 0 0;
  font-weight: 600;
}

:deep(.ant-card-head-title) {
  color: white !important;
  font-size: 18px;
}

:deep(.ant-card-head-title span) {
  color: white !important;
}

/* Collapse样式 */
:deep(.ant-collapse) {
  border: none;
  background: transparent;
}

:deep(.ant-collapse-item) {
  margin-bottom: 16px;
  border: 1px solid #e8e8e8;
  border-radius: 12px;
  overflow: hidden;
}

:deep(.ant-collapse-header) {
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  padding: 16px 20px !important;
  font-weight: 600;
}

:deep(.ant-collapse-content) {
  border-top: 1px solid #e8e8e8;
}

:deep(.ant-collapse-content-box) {
  padding: 20px;
}

/* 统计卡片样式 */
:deep(.ant-statistic-title) {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

:deep(.ant-statistic-content) {
  font-size: 24px;
  font-weight: 600;
  color: #1890ff;
}

/* 景点卡片样式 */
:deep(.ant-list-item) {
  transition: all 0.3s ease;
}

:deep(.ant-list-item:hover) {
  transform: scale(1.02);
}

/* 动画 */
@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .result-container {
    padding: 20px 10px;
  }

  .page-header {
    flex-direction: column;
    gap: 16px;
  }
}

/* ── 功能20: AI 行程调整 ── */
.ai-chat-fab {
  position: fixed;
  right: 24px;
  bottom: 80px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(102, 126, 234, 0.5);
  z-index: 999;
  transition: transform 0.2s, box-shadow 0.2s;
}
.ai-chat-fab:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.7);
}

.guide-chat-fab {
  position: fixed;
  right: 24px;
  bottom: 144px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, #13c2c2 0%, #08979c 100%);
  color: white;
  font-size: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(19, 194, 194, 0.5);
  z-index: 999;
  transition: transform 0.2s, box-shadow 0.2s;
}

.guide-chat-fab:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 20px rgba(8, 151, 156, 0.7);
}

.adjust-drawer-content {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 110px);
  gap: 16px;
}

.chat-history {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}

.chat-empty p {
  color: #888;
  font-size: 13px;
  margin-bottom: 12px;
}

.chat-examples {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chat-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  max-width: 90%;
}

.chat-bubble-user {
  background: #e8f4ff;
  align-self: flex-end;
  border-bottom-right-radius: 4px;
}

.chat-bubble-ai {
  background: #f6ffed;
  align-self: flex-start;
  border-bottom-left-radius: 4px;
}

.bubble-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.bubble-role {
  font-size: 11px;
  font-weight: 600;
  color: #555;
}

.bubble-time {
  font-size: 11px;
  color: #aaa;
}

.bubble-content {
  font-size: 13px;
  line-height: 1.5;
  color: #333;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-input-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-input-actions {
  display: flex;
  flex-direction: column;
}

.guide-context {
  margin-bottom: 8px;
  font-size: 13px;
  color: #666;
}

.guide-debug-toggle {
  padding: 8px 10px;
  border-radius: 8px;
  background: #f3fbff;
  border: 1px solid #d6f0ff;
}

.guide-debug-toggle-text {
  font-size: 12px;
  color: #3a4b57;
}

.guide-refs {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #d9d9d9;
}

.guide-refs-title {
  font-size: 12px;
  color: #777;
  margin-bottom: 6px;
}

.guide-debug-panel {
  margin-top: 10px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
  background: #fff;
}

.guide-debug-title {
  font-size: 12px;
  font-weight: 600;
  color: #5f6b7a;
  margin-bottom: 8px;
}

.guide-debug-tags {
  margin-bottom: 8px;
}

.guide-debug-block {
  margin-top: 6px;
}

.guide-debug-label {
  font-size: 12px;
  color: #78838f;
  margin-bottom: 4px;
}

.guide-debug-query-list {
  margin: 0;
  padding-left: 18px;
  color: #404a57;
  font-size: 12px;
  line-height: 1.5;
}
</style>

