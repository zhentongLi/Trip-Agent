<template>
  <div class="result">
    <!-- Background grid + glow -->
    <div class="bg-grid" />
    <div class="bg-glow result-glow" />

    <!-- ── Top action bar ───────────────────────────────────────────── -->
    <div class="action-bar">
      <div class="action-bar-line" />
      <a-button class="ab-btn" @click="goBack">← 返回</a-button>
      <div class="ab-spacer" />

      <template v-if="tripPlan">
        <a-button v-if="!editMode" class="ab-btn" @click="toggleEditMode">✏️ 编辑</a-button>
        <a-button v-else type="primary" @click="saveChanges">💾 保存</a-button>
        <a-button v-if="editMode" class="ab-btn" @click="cancelEdit">❌ 取消</a-button>

        <a-dropdown v-if="!editMode" :trigger="['click']">
          <a-button class="ab-btn">📥 导出 <DownOutlined /></a-button>
          <template #overlay>
            <a-menu @click="handleExportClick">
              <a-menu-item key="image">📷 导出为图片</a-menu-item>
              <a-menu-item key="pdf">📄 导出为PDF</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>

        <a-button v-if="!editMode" class="ab-btn" :loading="sharing" @click="handleShare">🔗 分享</a-button>
        <a-button v-if="!editMode" class="ab-btn" :loading="guiding" @click="openGuideDrawer()">🧭 导游问答</a-button>
        <a-button v-if="!editMode && isLoggedIn()" class="ab-btn" :loading="saving" @click="handleSaveCloud">☁️ 保存</a-button>
      </template>
    </div>

    <div v-if="tripPlan" class="result-body">
      <!-- ── Side nav ──────────────────────────────────────────────── -->
      <aside class="side-nav">
        <div
          v-for="nav in mainNavItems"
          :key="nav.key"
          class="side-item"
          :class="{ active: activeSection === nav.key }"
          @click="scrollToSection({ key: nav.key })"
        >
          <span class="side-active-bar" v-if="activeSection === nav.key" />
          {{ nav.label }}
        </div>

        <div class="side-section-label">每日行程</div>
        <div
          v-for="(_, idx) in tripPlan.days"
          :key="`day-${idx}`"
          class="side-day"
          :class="{ active: activeSection === `day-${idx}` }"
          @click="scrollToSection({ key: `day-${idx}` })"
        >
          第{{ idx + 1 }}天
        </div>

        <div
          v-if="tripPlan.weather_info && tripPlan.weather_info.length > 0"
          class="side-item"
          :class="{ active: activeSection === 'weather' }"
          @click="scrollToSection({ key: 'weather' })"
        >
          🌤️ 天气信息
        </div>
      </aside>

      <!-- ── Main content ──────────────────────────────────────────── -->
      <div class="main-content">
        <!-- Overview + Budget row -->
        <div class="overview-row">
          <div id="overview" class="info-card glass-card">
            <div class="card-title">{{ tripPlan.city }}旅行计划</div>
            <div class="info-row">
              <span class="info-label">📅 日期</span>
              <span class="info-value">{{ tripPlan.start_date }} 至 {{ tripPlan.end_date }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">💡 建议</span>
              <span class="info-value">{{ tripPlan.overall_suggestions }}</span>
            </div>
          </div>

          <div id="budget" v-if="tripPlan.budget" class="budget-card glass-card">
            <div class="card-title">💰 预算明细</div>
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
              <span class="budget-total-label">预估总费用</span>
              <span class="budget-total-value grad-text">¥{{ tripPlan.budget.total }}</span>
            </div>
          </div>
        </div>

        <!-- Map card -->
        <div id="map" class="map-card glass-card">
          <div class="card-title">📍 景点地图</div>
          <div id="amap-container" class="amap-container"></div>
        </div>

        <!-- 每日行程:可折叠 -->
        <a-card title="📅 每日行程" :bordered="false" class="days-card">
          <a-collapse v-model:activeKey="activeDays">
            <a-collapse-panel
              v-for="(day, index) in tripPlan.days"
              :key="index"
              :id="`day-${index}`"
            >
              <div
                class="day-head"
                :class="{ open: activeDays.includes(idx) }"
                @click="toggleDay(idx)"
              >
                <div class="day-index-badge" :class="{ active: activeDays.includes(idx) }">{{ idx + 1 }}</div>
                <span class="day-title">第{{ day.day_index + 1 }}天 · {{ day.description }}</span>
                <span class="day-date">{{ day.date }}</span>
                <button
                  class="day-audio-btn"
                  :class="{ playing: isSpeaking && speakingKey === `day-${idx}` }"
                  @click.stop="speak(daySpeakText(day), `day-${idx}`)"
                  :title="isSpeaking && speakingKey === `day-${idx}` ? '停止' : '朗读今日行程'"
                >{{ isSpeaking && speakingKey === `day-${idx}` ? '⏹' : '🔊' }}</button>
                <span class="day-toggle">{{ activeDays.includes(idx) ? '▲' : '▼' }}</span>
              </div>

              <div v-if="activeDays.includes(idx)" class="day-body">
                <div class="day-meta">
                  <span>🚗 {{ day.transportation }}</span>
                  <span>🏨 {{ day.accommodation }}</span>
                </div>

                <!-- Attractions -->
                <div class="attractions-grid">
                  <div
                    v-for="(item, attrIdx) in day.attractions"
                    :key="attrIdx"
                    class="attraction-card"
                  >
                    <div class="attr-image-wrap">
                      <img
                        :src="getAttractionImage(item.name, attrIdx)"
                        :alt="item.name"
                        class="attr-image"
                        @error="handleImageError"
                      />
                      <div class="attr-number">{{ attrIdx + 1 }}</div>
                      <div v-if="(item.ticket_price ?? 0) > 0" class="attr-price">¥{{ item.ticket_price }}</div>
                      <div v-else class="attr-price free">免费</div>
                    </div>

                    <div class="attr-body">
                      <div class="attr-name">{{ item.name }}</div>
                      <div class="attr-meta">
                        ⏱ {{ item.visit_duration }}分钟
                        <span v-if="item.rating"> · ⭐ {{ item.rating }}</span>
                      </div>

                      <div v-if="editMode" class="attr-edit">
                        <div class="edit-label">地址</div>
                        <a-input v-model:value="item.address" size="small" />
                        <div class="edit-label">游览时长(分钟)</div>
                        <a-input-number v-model:value="item.visit_duration" :min="10" :max="480" size="small" style="width:100%" />
                        <div class="edit-label">描述</div>
                        <a-textarea v-model:value="item.description" :rows="2" size="small" />
                        <div class="edit-actions">
                          <a-button size="small" @click="moveAttraction(day.day_index, attrIdx, 'up')" :disabled="attrIdx === 0">↑</a-button>
                          <a-button size="small" @click="moveAttraction(day.day_index, attrIdx, 'down')" :disabled="attrIdx === day.attractions.length - 1">↓</a-button>
                          <a-button size="small" danger @click="deleteAttraction(day.day_index, attrIdx)">🗑️</a-button>
                        </div>
                      </div>
                      <div v-else>
                        <div class="attr-detail">
                          <span class="attr-detail-label">📍</span>
                          <span>{{ item.address }}</span>
                        </div>
                        <div v-if="item.opening_hours" class="attr-detail">
                          <span class="attr-detail-label">⏰</span>
                          <span>{{ item.opening_hours }}</span>
                        </div>
                        <div class="attr-desc">{{ item.description }}</div>

                        <button class="link-btn" @click="openGuideDrawer(item.name)">🎙️ 获取导游解说</button>
                        <button
                          class="link-btn audio-btn"
                          :class="{ playing: isSpeaking && speakingKey === `attr-${item.name}` }"
                          @click="speak(attractionSpeakText(item), `attr-${item.name}`)"
                        >
                          {{ isSpeaking && speakingKey === `attr-${item.name}` ? '⏹ 停止朗读' : '🔊 朗读景点介绍' }}
                        </button>

                        <div class="booking-bar">
                          <span class="booking-label">🎟️</span>
                          <button class="booking-btn primary" @click="openBookingLink(getAttractionLinks(item.name, tripPlan!.city).ctrip, 'ctrip_attraction', item.name)">携程</button>
                          <button class="booking-btn primary" @click="openBookingLink(getAttractionLinks(item.name, tripPlan!.city).meituan, 'meituan_attraction', item.name)">美团</button>
                          <button class="booking-btn" @click="openBookingLink(getAttractionLinks(item.name, tripPlan!.city).damai, 'damai_attraction', item.name)">大麦网</button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Hotel -->
                <div v-if="day.hotel" class="hotel-block">
                  <div class="hotel-title">🏨 {{ day.hotel.name }}</div>
                  <div class="hotel-meta">
                    <span v-if="day.hotel.price_range">💰 {{ day.hotel.price_range }}</span>
                    <span v-if="day.hotel.rating">⭐ {{ day.hotel.rating }}</span>
                    <span v-if="day.hotel.distance">📏 {{ day.hotel.distance }}</span>
                    <span v-if="day.hotel.type">🏷️ {{ day.hotel.type }}</span>
                  </div>
                  <div class="hotel-address" v-if="day.hotel.address">{{ day.hotel.address }}</div>
                  <div class="booking-bar">
                    <span class="booking-label">🏨 预订</span>
                    <button class="booking-btn primary" @click="openBookingLink(getHotelLinks(day.hotel.name, tripPlan!.city, day.date, tripPlan!.end_date).ctrip, 'ctrip_hotel', day.hotel.name)">携程</button>
                    <button class="booking-btn" @click="openBookingLink(getHotelLinks(day.hotel.name, tripPlan!.city, day.date, tripPlan!.end_date).feizhu, 'feizhu_hotel', day.hotel.name)">飞猪</button>
                    <button class="booking-btn" @click="openBookingLink(getHotelLinks(day.hotel.name, tripPlan!.city, day.date, tripPlan!.end_date).meituan, 'meituan_hotel', day.hotel.name)">美团</button>
                  </div>
                </div>

                <!-- Meals -->
                <div class="meals-row">
                  <div v-for="meal in day.meals" :key="meal.type" class="meal-card">
                    <div class="meal-label">{{ getMealIcon(meal.type) }} {{ getMealLabel(meal.type) }}</div>
                    <div class="meal-name">{{ meal.name }}</div>
                    <div v-if="meal.description" class="meal-desc">{{ meal.description }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Weather -->
        <div
          v-if="tripPlan.weather_info && tripPlan.weather_info.length > 0"
          id="weather"
          class="weather-card glass-card"
        >
          <div class="card-title">🌤️ 天气信息</div>
          <div class="weather-grid">
            <div v-for="(w, i) in tripPlan.weather_info" :key="i" class="weather-item">
              <div class="weather-date">📅 {{ w.date }}</div>
              <div class="weather-row">
                <span class="weather-icon">☀️</span>
                <div>
                  <div class="weather-sub">白天</div>
                  <div class="weather-text">{{ w.day_weather }} {{ w.day_temp }}°C</div>
                </div>
              </div>
              <div class="weather-row">
                <span class="weather-icon">🌙</span>
                <div>
                  <div class="weather-sub">夜间</div>
                  <div class="weather-text">{{ w.night_weather }} {{ w.night_temp }}°C</div>
                </div>
              </div>
              <div class="weather-wind">💨 {{ w.wind_direction }} {{ w.wind_power }}</div>
              <div v-if="w.weather_warning" class="weather-warning">🚨 {{ w.weather_warning }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Empty state ───────────────────────────────────────────────── -->
    <div v-else class="empty-state">
      <div class="empty-icon">🗺️</div>
      <div class="empty-text">暂无旅行计划数据，请先创建行程</div>
      <a-button type="primary" @click="goBack">返回首页创建行程</a-button>
    </div>

    <!-- ── Floating action buttons ───────────────────────────────────── -->
    <button
      v-if="tripPlan"
      class="fab fab-adjust"
      :class="{ shifted: showAdjustDrawer || showGuideDrawer }"
      @click="showAdjustDrawer = true"
      title="AI 调整行程"
    >🤖</button>

    <button
      v-if="tripPlan"
      class="fab fab-guide"
      :class="{ shifted: showAdjustDrawer || showGuideDrawer }"
      @click="openGuideDrawer()"
      title="导游RAG问答"
    >🧭</button>

    <!-- ── AI Adjust Drawer ──────────────────────────────────────────── -->
    <a-drawer
      v-model:open="showAdjustDrawer"
      title="🤖 AI 行程调整"
      placement="right"
      :width="420"
    >
      <div class="drawer-body">
        <div class="chat-history" ref="chatHistoryRef">
          <div v-if="chatMessages.length === 0" class="chat-empty">
            <p>💡 用自然语言描述你想改什么：</p>
            <div class="chat-examples">
              <div class="chat-example example-blue" @click="fillExample('把第二天的第一个景点换成大猫山景区')">📌 把第二天第一个景点换成大猫山景区</div>
              <div class="chat-example example-green" @click="fillExample('第三天加一个晚上看演出的地方')">🎬 第三天加晚上看演出的地方</div>
              <div class="chat-example example-purple" @click="fillExample('把每天的早餐改成袋粥/稀饭类小吃')">🍚 每天早餐改成稀饭类小吃</div>
              <div class="chat-example example-orange" @click="fillExample('把住宿改成民宿风格')">🏡 把住宿改成民宿风格</div>
            </div>
          </div>
          <div
            v-for="(msg, idx) in chatMessages"
            :key="idx"
            class="chat-bubble-row"
            :class="msg.role === 'user' ? 'is-user' : 'is-ai'"
          >
            <div class="bubble-meta">{{ msg.role === 'user' ? '👤 我' : '🤖 AI' }} · {{ msg.timestamp }}</div>
            <div class="bubble-content" :class="msg.role === 'user' ? 'bubble-user' : 'bubble-ai'">
              {{ msg.content }}
            </div>
          </div>
          <div v-if="adjusting" class="chat-typing">🤖 正在调整行程，稍等...</div>
        </div>

        <div class="drawer-input">
          <a-textarea
            v-model:value="adjustInput"
            placeholder="描述你想如何修改行程... (Ctrl+Enter 发送)"
            :rows="3"
            :maxlength="500"
            show-count
            :disabled="adjusting"
            @keydown.ctrl.enter="handleAdjust"
          />
          <button class="send-btn" :disabled="adjusting" @click="handleAdjust">
            <span v-if="adjusting" class="spinner" /> {{ adjusting ? '处理中...' : '🚀 发送 (Ctrl+Enter)' }}
          </button>
          <button class="clear-btn" :disabled="chatMessages.length === 0" @click="chatMessages = []">
            🗑️ 清空对话记录
          </button>
        </div>
      </div>
    </a-drawer>

    <!-- ── Guide RAG Drawer ──────────────────────────────────────────── -->
    <a-drawer
      v-model:open="showGuideDrawer"
      title="🧭 导游RAG模式"
      placement="right"
      :width="460"
    >
      <div class="drawer-body">
        <div v-if="isDevEnv" class="guide-debug-toggle">
          <a-switch v-model:checked="guideDebugEnabled" size="small" />
          <span class="guide-debug-toggle-text">调试模式（显示 Skill/RAG 命中详情）</span>
          <a-tag color="processing">会话: {{ shortGuideSessionId(guideSessionId) }}</a-tag>
        </div>
        <div class="guide-context" v-if="guideAttractionName">
          当前景点上下文：<a-tag color="blue">{{ guideAttractionName }}</a-tag>
        </div>

        <div class="chat-history" ref="guideHistoryRef">
          <div v-if="guideMessages.length === 0" class="chat-empty">
            <p>💡 可提问示例：</p>
            <div class="chat-examples">
              <div class="chat-example example-blue" @click="fillGuideExample('这个行程里最值得早起去的景点是哪个？为什么？')">🌅 哪个景点最适合早去？</div>
              <div class="chat-example example-green" @click="fillGuideExample('请给我一份今天的游览顺序和避坑建议')">🗺️ 今日游览顺序+避坑建议</div>
              <div class="chat-example example-orange" @click="fillGuideExample('预算有限，哪些景点可以缩短停留时间？')">💰 预算有限如何优化时间？</div>
            </div>
          </div>

          <div
            v-for="(msg, idx) in guideMessages"
            :key="`guide-${idx}`"
            class="chat-bubble-row"
            :class="msg.role === 'user' ? 'is-user' : 'is-ai'"
          >
            <div class="bubble-meta">{{ msg.role === 'user' ? '👤 我' : '🧭 导游AI' }} · {{ msg.timestamp }}</div>
            <div class="bubble-content" :class="msg.role === 'user' ? 'bubble-user' : 'bubble-ai'">
              {{ msg.content }}
            </div>
            <button
              v-if="msg.role === 'assistant'"
              class="link-btn audio-btn guide-audio-btn"
              :class="{ playing: isSpeaking && speakingKey === `guide-${idx}` }"
              @click="speak(msg.content, `guide-${idx}`)"
            >{{ isSpeaking && speakingKey === `guide-${idx}` ? '⏹ 停止朗读' : '🔊 朗读解说' }}</button>
            <div v-if="msg.references && msg.references.length > 0" class="guide-refs">
              <div class="guide-refs-title">参考资料</div>
              <a-space wrap>
                <a-tag v-for="(ref, rIdx) in msg.references" :key="rIdx" color="geekblue">{{ ref.title }}</a-tag>
              </a-space>
            </div>
            <div v-if="isDevEnv && msg.debugMeta" class="guide-debug-panel">
              <div class="guide-debug-title">🧪 调试面板</div>
              <a-space wrap size="small">
                <a-tag color="purple">Skill: {{ msg.debugMeta.skill_meta?.skill_name || '-' }}</a-tag>
                <a-tag :color="msg.debugMeta.retrieval_meta?.has_local_kb_hit ? 'success' : 'error'">
                  本地知识库: {{ msg.debugMeta.retrieval_meta?.has_local_kb_hit ? '是' : '否' }}
                </a-tag>
                <a-tag :color="msg.debugMeta.retrieval_meta?.vector_store_enabled ? 'blue' : 'default'">
                  向量库: {{ msg.debugMeta.retrieval_meta?.vector_store_enabled ? '启用' : '关闭' }}
                </a-tag>
                <a-tag color="geekblue">重排: {{ msg.debugMeta.retrieval_meta?.reranker_mode || '-' }}</a-tag>
                <a-tag color="cyan">迭代轮次: {{ msg.debugMeta.retrieval_meta?.iterative_rounds ?? 0 }}</a-tag>
              </a-space>

              <div v-if="sourceCountEntries(msg.debugMeta.retrieval_meta?.source_counts).length > 0" class="guide-debug-block">
                <div class="guide-debug-label">来源统计</div>
                <a-space wrap size="small">
                  <a-tag
                    v-for="([source, count], sIdx) in sourceCountEntries(msg.debugMeta.retrieval_meta?.source_counts)"
                    :key="`source-${idx}-${sIdx}`"
                    color="blue"
                  >{{ formatSourceLabel(source) }}: {{ count }}</a-tag>
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
                  >{{ query }}</li>
                </ol>
              </div>
            </div>
          </div>
          <div v-if="guiding" class="chat-typing">🧭 正在检索资料并生成解说...</div>
        </div>

        <div class="drawer-input">
          <a-textarea
            v-model:value="guideInput"
            placeholder="例如：这个景点的最佳游览时段和拍照位是什么？(Ctrl+Enter 发送)"
            :rows="3"
            :maxlength="500"
            show-count
            :disabled="guiding"
            @keydown.ctrl.enter="handleGuideAsk"
          />
          <button class="send-btn guide" :disabled="guiding" @click="handleGuideAsk">
            <span v-if="guiding" class="spinner" /> {{ guiding ? '检索中...' : '🎙️ 发送提问 (Ctrl+Enter)' }}
          </button>
          <button class="clear-btn" :disabled="guideMessages.length === 0" @click="guideMessages = []">
            🗑️ 清空导游对话
          </button>
        </div>
      </div>
    </a-drawer>

    <!-- Back to top -->
    <a-back-top :visibility-height="300">
      <div class="back-top-btn">↑</div>
    </a-back-top>
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
import { getAttractionLinks, getHotelLinks, openBookingLink } from '@/services/booking'
import { speak, isSpeaking, speakingKey } from '@/services/audio'

const router = useRouter()
const route = useRoute()
const tripPlan = ref<TripPlan | null>(null)
const editMode = ref(false)
const originalPlan = ref<TripPlan | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const activeSection = ref('overview')
const activeDays = ref<number[]>([])
const sharing = ref(false)
const saving = ref(false)
const showAdjustDrawer = ref(false)
const adjustInput = ref('')
const adjusting = ref(false)
const chatMessages = ref<AdjustChatEntry[]>([])
const chatHistoryRef = ref<HTMLDivElement | null>(null)

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

const mainNavItems = [
  { key: 'overview', label: '📋 行程概览' },
  { key: 'budget', label: '💰 预算明细' },
  { key: 'map', label: '📍 景点地图' },
]

const loadPlanData = async () => {
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
    const data = sessionStorage.getItem('tripPlan')
    if (data) {
      tripPlan.value = JSON.parse(data)
      if (tripPlan.value) {
        try { saveHistory(tripPlan.value) } catch {}
      }
    }
  }

  attractionPhotos.value = {}
  if (map) { map.destroy(); map = null }

  if (tripPlan.value) {
    activeDays.value = tripPlan.value.days.map((_, i) => i)
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
    if (newPath !== oldPath) await loadPlanData()
  }
)

// Share
const handleShare = async () => {
  if (!tripPlan.value) return
  sharing.value = true
  try {
    const result = await createShare(tripPlan.value, `${tripPlan.value.city} ${tripPlan.value.start_date} 行程`)
    const shareUrl = result.share_url.startsWith('http')
      ? result.share_url
      : `${window.location.origin}${result.share_url.startsWith('/') ? '' : '/'}${result.share_url}`
    await navigator.clipboard.writeText(shareUrl)
    message.success({ content: `🔗 分享链接已复制！ID: ${result.share_id}（7天内有效）`, duration: 5 })
  } catch (e: any) {
    message.error(`分享失败: ${e.message}`)
  } finally {
    sharing.value = false
  }
}

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

const fillExample = (text: string) => { adjustInput.value = text }
const fillGuideExample = (text: string) => { guideInput.value = text }

const scrollChatToBottom = async () => {
  await nextTick()
  if (chatHistoryRef.value) chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight
}
const scrollGuideToBottom = async () => {
  await nextTick()
  if (guideHistoryRef.value) guideHistoryRef.value.scrollTop = guideHistoryRef.value.scrollHeight
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
  const map: Record<string, string> = { knowledge_base: '本地知识库', trip_plan: '当前行程' }
  return map[source] || source
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

  const timestamp = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  chatMessages.value.push({ role: 'user', content: msg, timestamp })
  adjustInput.value = ''
  adjusting.value = true
  await scrollChatToBottom()

  try {
    const newPlan = await adjustTripPlan(tripPlan.value, msg)
    tripPlan.value = newPlan
    sessionStorage.setItem('tripPlan', JSON.stringify(newPlan))
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
      content: `❌ 调整失败：${e.message}。请重试或将该要求描述得更具体。`,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    })
    message.error(`AI 调整失败: ${e.message}`)
  } finally {
    adjusting.value = false
    await scrollChatToBottom()
  }
}

const goBack = () => router.push('/')

const scrollToSection = ({ key }: { key: string }) => {
  activeSection.value = key
  const element = document.getElementById(key)
  if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const toggleEditMode = () => {
  editMode.value = true
  originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))
  message.info('进入编辑模式')
}

const saveChanges = () => {
  editMode.value = false
  if (tripPlan.value) sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan.value))
  message.success('修改已保存')
  if (map) map.destroy()
  nextTick(() => initMap())
}

const cancelEdit = () => {
  if (originalPlan.value) tripPlan.value = JSON.parse(JSON.stringify(originalPlan.value))
  editMode.value = false
  message.info('已取消编辑')
}

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

const moveAttraction = (dayIndex: number, attrIndex: number, direction: 'up' | 'down') => {
  if (!tripPlan.value) return
  const attractions = tripPlan.value.days[dayIndex].attractions
  if (direction === 'up' && attrIndex > 0) {
    [attractions[attrIndex], attractions[attrIndex - 1]] = [attractions[attrIndex - 1], attractions[attrIndex]]
  } else if (direction === 'down' && attrIndex < attractions.length - 1) {
    [attractions[attrIndex], attractions[attrIndex + 1]] = [attractions[attrIndex + 1], attractions[attrIndex]]
  }
}

const toggleDay = (idx: number) => {
  if (activeDays.value.includes(idx)) activeDays.value = activeDays.value.filter(x => x !== idx)
  else activeDays.value = [...activeDays.value, idx]
}

// ── TTS 朗读文本构建 ──────────────────────────────────────────────────────
function attractionSpeakText(item: { name: string; description: string; address: string; visit_duration: number; ticket_price?: number }): string {
  const ticket = (item.ticket_price ?? 0) > 0 ? `门票${item.ticket_price}元。` : '免费景点。'
  return `${item.name}。${item.description}。地址：${item.address}。建议游览时间${item.visit_duration}分钟。${ticket}`
}

function daySpeakText(day: { date: string; day_index: number; description: string; attractions: Array<{ name: string }>; hotel?: { name: string } | null }): string {
  const attractions = day.attractions.map(a => a.name).join('、')
  const hotel = day.hotel ? `推荐住宿：${day.hotel.name}。` : ''
  return `第${day.day_index + 1}天，${day.date}。${day.description}。今日景点：${attractions}。${hotel}`
}

const getMealLabel = (type: string): string => {
  return { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '小吃' }[type] || type
}
const getMealIcon = (type: string): string => {
  return { breakfast: '🌅', lunch: '☀️', dinner: '🌙', snack: '🍡' }[type] || '🍽️'
}

const loadAttractionPhotos = async () => {
  if (!tripPlan.value) return
  const promises: Promise<void>[] = []
  const city = tripPlan.value.city ?? ''
  tripPlan.value.days.forEach(day => {
    day.attractions.forEach(attraction => {
      const promise = fetch(`http://localhost:8000/api/poi/photo?name=${encodeURIComponent(attraction.name)}&city=${encodeURIComponent(city)}`)
        .then(res => res.json())
        .then(data => {
          if (data.success && data.data.photo_url) attractionPhotos.value[attraction.name] = data.data.photo_url
        })
        .catch(err => console.error(`获取${attraction.name}图片失败:`, err))
      promises.push(promise)
    })
  })
  await Promise.all(promises)
}

const getAttractionImage = (name: string, index: number): string => {
  if (attractionPhotos.value[name]) return attractionPhotos.value[name]
  const colors = [
    { start: '#667eea', end: '#764ba2' },
    { start: '#f093fb', end: '#f5576c' },
    { start: '#4facfe', end: '#00f2fe' },
    { start: '#43e97b', end: '#38f9d7' },
    { start: '#fa709a', end: '#fee140' },
  ]
  const { start, end } = colors[index % colors.length]
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><defs><linearGradient id="grad${index}" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:${start};stop-opacity:1"/><stop offset="100%" style="stop-color:${end};stop-opacity:1"/></linearGradient></defs><rect width="400" height="300" fill="url(#grad${index})"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="24" font-weight="bold" fill="white">${name}</text></svg>`
  return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
}

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="300"%3E%3Crect width="400" height="300" fill="%231a1a2e"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="%23667eea"%3E图片加载失败%3C/text%3E%3C/svg%3E'
}

// ── Export ─────────────────────────────────────────────────────────────
const handleExportClick = ({ key }: { key: string }) => {
  if (key === 'image') exportAsImage()
  else if (key === 'pdf') exportAsPDF()
}

const exportAsImage = async () => {
  try {
    message.loading({ content: '正在生成图片...', key: 'export', duration: 0 })
    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) throw new Error('未找到内容元素')

    const canvas = await html2canvas(element, {
      backgroundColor: '#080810',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true,
    })

    const link = document.createElement('a')
    link.download = `旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
    message.success({ content: '图片导出成功！', key: 'export' })
  } catch (error: any) {
    console.error('导出图片失败:', error)
    message.error({ content: `导出图片失败: ${error.message}`, key: 'export' })
  }
}

const exportAsPDF = async () => {
  if (!tripPlan.value) return
  try {
    message.loading({ content: '正在生成 PDF...', key: 'export', duration: 0 })
    await exportTripPdfBackend(tripPlan.value)
    message.success({ content: '📄 PDF 导出成功！', key: 'export', duration: 3 })
  } catch (error: any) {
    console.error('导出 PDF 失败:', error)
    message.error({ content: `导出 PDF 失败: ${error.message}`, key: 'export' })
  }
}

// ── AMap ──────────────────────────────────────────────────────────────
const initMap = async () => {
  try {
    const AMap = await AMapLoader.load({
      key: import.meta.env.VITE_AMAP_WEB_JS_KEY,
      version: '2.0',
      plugins: ['AMap.Marker', 'AMap.Polyline', 'AMap.InfoWindow'],
    })
    map = new AMap.Map('amap-container', { zoom: 12, viewMode: '3D' })
    if (tripPlan.value?.city) map.setCity(tripPlan.value.city)
    addAttractionMarkers(AMap)
  } catch (error) {
    console.error('地图加载失败:', error)
    message.error('地图加载失败')
  }
}

const addAttractionMarkers = (AMap: any) => {
  if (!tripPlan.value) return
  const markers: any[] = []
  const allAttractions: any[] = []
  tripPlan.value.days.forEach((day, dayIndex) => {
    day.attractions.forEach((attraction, attrIndex) => {
      if (attraction.location && attraction.location.longitude && attraction.location.latitude) {
        allAttractions.push({ ...attraction, dayIndex, attrIndex })
      }
    })
  })

  allAttractions.forEach((attraction, index) => {
    const marker = new AMap.Marker({
      position: [attraction.location.longitude, attraction.location.latitude],
      title: attraction.name,
      label: {
        content: `<div style="background: linear-gradient(135deg,#667eea,#764ba2); color: white; padding: 4px 8px; border-radius: 6px; font-size: 12px; box-shadow: 0 0 8px rgba(102,126,234,0.6);">${index + 1}</div>`,
        offset: new AMap.Pixel(0, -30),
      },
    })
    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding: 10px;">
          <h4 style="margin: 0 0 8px 0;">${attraction.name}</h4>
          <p style="margin: 4px 0;"><strong>地址:</strong> ${attraction.address}</p>
          <p style="margin: 4px 0;"><strong>游览时长:</strong> ${attraction.visit_duration}分钟</p>
          <p style="margin: 4px 0;"><strong>描述:</strong> ${attraction.description}</p>
          <p style="margin: 4px 0; color: #667eea;"><strong>第${attraction.dayIndex + 1}天 景点${attraction.attrIndex + 1}</strong></p>
        </div>`,
      offset: new AMap.Pixel(0, -30),
    })
    marker.on('click', () => infoWindow.open(map, marker.getPosition()))
    markers.push(marker)
  })

  map.add(markers)
  if (allAttractions.length > 0) map.setFitView(markers)
  drawRoutes(AMap, allAttractions)
}

const drawRoutes = (AMap: any, attractions: any[]) => {
  if (attractions.length < 2) return
  const dayGroups: any = {}
  attractions.forEach(attr => {
    if (!dayGroups[attr.dayIndex]) dayGroups[attr.dayIndex] = []
    dayGroups[attr.dayIndex].push(attr)
  })
  Object.values(dayGroups).forEach((dayAttractions: any) => {
    if (dayAttractions.length < 2) return
    const path = dayAttractions.map((attr: any) => [attr.location.longitude, attr.location.latitude])
    const polyline = new AMap.Polyline({
      path,
      strokeColor: '#a78bfa',
      strokeWeight: 4,
      strokeOpacity: 0.85,
      strokeStyle: 'solid',
      showDir: true,
    })
    map.add(polyline)
  })
}
</script>

<style scoped>
.result {
  display: flex;
  flex-direction: column;
  flex: 1;
  /* 视口高度减去 header(52px)，内容超出由 .main-content 内部滚动 */
  height: calc(100vh - 52px);
  background: var(--bg-base);
  position: relative;
  overflow: hidden;
}

.result-glow {
  top: -10%;
  right: -5%;
  width: 400px;
  height: 400px;
  background: rgba(102, 126, 234, 0.08);
}

/* ── Action bar ──────────────────────────────────────────────────── */
.action-bar {
  background: rgba(8, 8, 16, 0.9);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(102, 126, 234, 0.15);
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  position: relative;
  z-index: 5;
}
.action-bar-line {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(102,126,234,0.3), transparent);
}
.ab-spacer { flex: 1; }
.ab-btn {
  height: 32px;
  padding: 0 12px;
}

/* ── Body layout ─────────────────────────────────────────────────── */
.result-body {
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

/* Side nav */
.side-nav {
  width: 180px;
  background: rgba(255, 255, 255, 0.02);
  border-right: 1px solid rgba(102, 126, 234, 0.1);
  padding: 14px 0;
  flex-shrink: 0;
  overflow-y: auto;
}
.side-item {
  padding: 9px 16px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.38);
  cursor: pointer;
  position: relative;
  transition: all 0.18s;
}
.side-item:hover { color: var(--text-secondary); }
.side-item.active {
  color: white;
  background: rgba(102, 126, 234, 0.1);
}
.side-active-bar {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 2px;
  background: linear-gradient(180deg, #667eea, #a78bfa);
  box-shadow: 0 0 8px #667eea;
}
.side-section-label {
  padding: 10px 16px 4px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 2px;
  color: rgba(255, 255, 255, 0.2);
  text-transform: uppercase;
  margin-top: 8px;
}
.side-day {
  padding: 8px 16px 8px 24px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  transition: all 0.18s;
}
.side-day:hover { color: var(--text-secondary); }
.side-day.active {
  color: #a5b4fc;
  background: rgba(102, 126, 234, 0.08);
}

/* Main content */
.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 700;
  color: white;
  margin-bottom: 12px;
}

/* Overview + Budget row */
.overview-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.info-card, .budget-card {
  padding: 18px;
}
.info-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
  line-height: 1.6;
}
.info-label {
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}
.info-value {
  color: var(--text-secondary);
  flex: 1;
}

/* Budget */
.budget-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
}
.budget-item {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 10px;
  padding: 9px 12px;
}
.budget-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}
.budget-value {
  font-size: 17px;
  font-weight: 700;
  color: white;
  margin-top: 2px;
}
.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
  padding-top: 10px;
}
.budget-total-label {
  font-size: 12px;
  color: var(--text-muted);
}
.budget-total-value {
  font-size: 22px;
  font-weight: 800;
}

/* Map */
.map-card {
  padding: 18px;
}
.amap-container {
  width: 100%;
  height: 400px;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.02);
}

/* Days */
.days-card { padding: 18px; }
.days-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.day-block {
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 12px;
  overflow: hidden;
}
.day-head {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  background: rgba(255, 255, 255, 0.02);
  transition: background 0.2s;
}
.day-head.open {
  background: rgba(102, 126, 234, 0.1);
}
.day-head:hover {
  background: rgba(102, 126, 234, 0.06);
}
.day-index-badge {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: white;
  margin-right: 12px;
  flex-shrink: 0;
  transition: background 0.2s;
}
.day-index-badge.active {
  background: var(--brand-gradient);
  box-shadow: var(--brand-glow-sm);
}
.day-title {
  font-size: 13px;
  font-weight: 600;
  color: white;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.day-date {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.3);
  margin-right: 12px;
}
.day-toggle {
  color: rgba(102, 126, 234, 0.7);
  font-size: 12px;
}

.day-body {
  padding: 14px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}
.day-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 14px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
  flex-wrap: wrap;
}

/* Attractions */
.attractions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.attraction-card {
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 10px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.02);
  display: flex;
  flex-direction: column;
}
.attr-image-wrap {
  height: 120px;
  position: relative;
  overflow: hidden;
}
.attr-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.attr-number {
  position: absolute;
  top: 6px; left: 6px;
  width: 22px; height: 22px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 800;
  color: #667eea;
  box-shadow: 0 2px 6px rgba(0,0,0,0.3);
}
.attr-price {
  position: absolute;
  bottom: 6px; right: 6px;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  font-size: 11px;
  border-radius: 4px;
  padding: 2px 6px;
  font-weight: 600;
}
.attr-price.free {
  background: rgba(52, 199, 89, 0.75);
}
.attr-body {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.attr-name {
  font-weight: 600;
  font-size: 13px;
  color: white;
}
.attr-meta {
  font-size: 10px;
  color: var(--text-muted);
}
.attr-detail {
  font-size: 11px;
  color: var(--text-secondary);
  display: flex;
  gap: 4px;
  align-items: flex-start;
}
.attr-detail-label { flex-shrink: 0; }
.attr-desc {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.5;
  margin-top: 2px;
}

.attr-edit {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.edit-label {
  font-size: 10px;
  color: var(--text-muted);
}
.edit-actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
}

.link-btn {
  background: none;
  border: none;
  color: #a5b4fc;
  font-size: 11px;
  padding: 4px 0;
  text-align: left;
}
.link-btn:hover { color: white; }

/* 🔊 朗读按钮 */
.audio-btn {
  color: rgba(102, 126, 234, 0.7);
  transition: color 0.18s;
}
.audio-btn:hover { color: #a5b4fc; }
.audio-btn.playing {
  color: #43e97b;
  animation: pulse 1.4s ease-in-out infinite;
}

/* 日程头部 🔊 按钮 */
.day-audio-btn {
  background: none;
  border: none;
  font-size: 13px;
  padding: 2px 6px;
  border-radius: 6px;
  color: rgba(102, 126, 234, 0.5);
  cursor: pointer;
  transition: all 0.18s;
  margin-right: 4px;
  flex-shrink: 0;
}
.day-audio-btn:hover { color: #a5b4fc; background: rgba(102,126,234,0.1); }
.day-audio-btn.playing {
  color: #43e97b;
  animation: pulse 1.4s ease-in-out infinite;
}

/* 导游抽屉朗读按钮 */
.guide-audio-btn {
  margin-top: 4px;
  display: block;
}
.link-btn:hover { color: white; }

/* Booking bar */
.booking-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  align-items: center;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed rgba(255, 255, 255, 0.06);
}
.booking-label {
  font-size: 10px;
  color: var(--text-muted);
  margin-right: 2px;
}
.booking-btn {
  height: 22px;
  padding: 0 8px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text-secondary);
  transition: all 0.18s;
}
.booking-btn:hover {
  background: rgba(102, 126, 234, 0.15);
  border-color: rgba(102, 126, 234, 0.4);
  color: white;
}
.booking-btn.primary {
  background: rgba(102, 126, 234, 0.15);
  border-color: rgba(102, 126, 234, 0.5);
  color: #a5b4fc;
}
.booking-btn.primary:hover {
  background: rgba(102, 126, 234, 0.25);
  color: white;
}

/* Hotel block */
.hotel-block {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.hotel-title {
  font-weight: 600;
  font-size: 13px;
  color: white;
  margin-bottom: 6px;
}
.hotel-meta {
  display: flex;
  gap: 14px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.hotel-address {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

/* Meals */
.meals-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
}
.meal-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  padding: 8px 10px;
}
.meal-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
  margin-bottom: 2px;
}
.meal-name {
  font-size: 12px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.85);
}
.meal-desc {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* Weather */
.weather-card { padding: 18px; }
.weather-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.weather-item {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 12px;
  padding: 14px 16px;
}
.weather-date {
  font-weight: 600;
  color: rgba(255, 255, 255, 0.75);
  font-size: 12px;
  margin-bottom: 10px;
}
.weather-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
.weather-icon { font-size: 16px; }
.weather-sub {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.3);
}
.weather-text {
  font-size: 12px;
  color: white;
}
.weather-wind {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
  margin-top: 4px;
}
.weather-warning {
  margin-top: 6px;
  background: rgba(250, 140, 22, 0.12);
  border: 1px solid rgba(250, 140, 22, 0.3);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  color: #fa8c16;
}

/* Empty state */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 60px 20px;
  position: relative;
  z-index: 1;
}
.empty-icon { font-size: 80px; opacity: 0.4; }
.empty-text {
  color: var(--text-muted);
  font-size: 14px;
}

/* FABs */
.fab {
  position: fixed;
  right: 20px;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  color: white;
  font-size: 20px;
  border: none;
  z-index: 100;
  transition: right 0.3s ease, transform 0.2s;
}
.fab.shifted { right: 440px; }
.fab:hover { transform: scale(1.08); }
.fab-adjust {
  bottom: 78px;
  background: var(--brand-gradient);
  box-shadow: 0 0 20px rgba(102, 126, 234, 0.5);
}
.fab-guide {
  bottom: 20px;
  background: linear-gradient(135deg, #43e97b, #38f9d7);
  box-shadow: 0 0 16px rgba(67, 233, 123, 0.45);
}

/* Drawer body */
.drawer-body {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.chat-history {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 10px;
}
.chat-empty {
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 12px;
}
.chat-empty p { margin-bottom: 8px; }
.chat-examples {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.chat-example {
  padding: 7px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.18s;
}
.example-blue {
  background: rgba(102, 126, 234, 0.1);
  border: 1px solid rgba(102, 126, 234, 0.25);
  color: #a5b4fc;
}
.example-blue:hover { background: rgba(102, 126, 234, 0.18); }
.example-green {
  background: rgba(52, 199, 89, 0.08);
  border: 1px solid rgba(52, 199, 89, 0.2);
  color: #34c759;
}
.example-green:hover { background: rgba(52, 199, 89, 0.15); }
.example-purple {
  background: rgba(167, 139, 250, 0.1);
  border: 1px solid rgba(167, 139, 250, 0.25);
  color: #c084fc;
}
.example-purple:hover { background: rgba(167, 139, 250, 0.18); }
.example-orange {
  background: rgba(250, 140, 22, 0.08);
  border: 1px solid rgba(250, 140, 22, 0.2);
  color: #fa8c16;
}
.example-orange:hover { background: rgba(250, 140, 22, 0.15); }

.chat-bubble-row {
  display: flex;
  flex-direction: column;
  margin-bottom: 10px;
}
.chat-bubble-row.is-user { align-items: flex-end; }
.chat-bubble-row.is-ai { align-items: flex-start; }
.bubble-meta {
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 3px;
}
.bubble-content {
  max-width: 85%;
  padding: 9px 13px;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-wrap: break-word;
}
.bubble-user {
  border-radius: 14px 14px 4px 14px;
  background: var(--brand-gradient);
  color: white;
}
.bubble-ai {
  border-radius: 14px 14px 14px 4px;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.85);
}
.chat-typing {
  color: var(--text-muted);
  font-size: 12px;
  padding: 4px 0;
}

/* Drawer input */
.drawer-input {
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.send-btn {
  height: 38px;
  border-radius: 10px;
  background: var(--brand-gradient);
  border: none;
  color: white;
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.send-btn.guide {
  background: linear-gradient(135deg, #43e97b, #38f9d7);
}
.send-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.clear-btn {
  height: 30px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text-muted);
  font-size: 11px;
}
.clear-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.clear-btn:not(:disabled):hover {
  color: white;
  border-color: rgba(255, 77, 79, 0.4);
  background: rgba(255, 77, 79, 0.08);
}

/* Guide drawer specifics */
.guide-debug-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
  flex-wrap: wrap;
}
.guide-debug-toggle-text {
  font-size: 11px;
  color: var(--text-secondary);
}
.guide-context {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}
.guide-refs {
  margin-top: 6px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}
.guide-refs-title {
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.guide-debug-panel {
  margin-top: 8px;
  padding: 10px;
  background: rgba(167, 139, 250, 0.06);
  border: 1px solid rgba(167, 139, 250, 0.2);
  border-radius: 8px;
}
.guide-debug-title {
  font-size: 11px;
  font-weight: 600;
  color: #c084fc;
  margin-bottom: 6px;
}
.guide-debug-block {
  margin-top: 8px;
}
.guide-debug-label {
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.guide-debug-query-list {
  margin: 0;
  padding-left: 18px;
  color: var(--text-secondary);
  font-size: 11px;
}
.guide-debug-query-list li {
  margin-bottom: 2px;
}

/* Spinner */
.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}

/* Back-to-top button */
.back-top-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--brand-gradient);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  box-shadow: var(--brand-glow);
  cursor: pointer;
}

/* Responsive */
@media (max-width: 768px) {
  .result-body { flex-direction: column; }
  .side-nav { width: 100%; display: flex; flex-wrap: wrap; padding: 8px; }
  .side-item, .side-day { padding: 6px 10px; }
  .side-section-label { width: 100%; }
  .overview-row { grid-template-columns: 1fr; }
  .fab.shifted { right: 20px; }
}
</style>
