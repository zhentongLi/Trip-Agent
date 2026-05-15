/**
 * ElevenLabs TTS 音频服务
 *
 * - 全局单实例播放器：同一时刻只有一段音频播放
 * - speak(text)  → 请求后端 /api/audio/speak，播放返回的 MP3
 * - stop()       → 停止当前播放
 * - isPlaying()  → 当前是否在播放
 * - isSpeaking   → 响应式 ref，可直接绑到模板
 */

import { ref } from 'vue'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// 响应式播放状态（可在模板中用 v-if / :class 绑定）
export const isSpeaking = ref(false)
export const speakingKey = ref<string>('')   // 标记当前朗读的文本 key

let _audio: HTMLAudioElement | null = null
let _objectUrl: string | null = null

function _cleanup() {
  if (_audio) {
    _audio.pause()
    _audio.src = ''
    _audio = null
  }
  if (_objectUrl) {
    URL.revokeObjectURL(_objectUrl)
    _objectUrl = null
  }
  isSpeaking.value = false
  speakingKey.value = ''
}

/**
 * 朗读指定文本。若当前有音频正在播放则先停止。
 * @param text  要朗读的文字（后端自动截断至 500 字）
 * @param key   可选标识符，用于在 UI 上高亮"正在朗读"的元素
 */
export async function speak(text: string, key = ''): Promise<void> {
  // 同一段文字再次点击 → 停止（toggle 行为）
  if (isSpeaking.value && speakingKey.value === key) {
    stop()
    return
  }

  _cleanup()

  isSpeaking.value = true
  speakingKey.value = key

  try {
    const resp = await fetch(`${API_BASE}/api/audio/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })

    if (!resp.ok || resp.headers.get('X-TTS-Error')) {
      console.warn('[audio] TTS 服务不可用 status=', resp.status)
      isSpeaking.value = false
      speakingKey.value = ''
      return
    }

    const blob = await resp.blob()
    _objectUrl = URL.createObjectURL(blob)
    _audio = new Audio(_objectUrl)
    _audio.onended = _cleanup
    _audio.onerror = _cleanup
    await _audio.play()
  } catch (err) {
    console.warn('[audio] speak error:', err)
    _cleanup()
  }
}

/** 停止当前播放 */
export function stop(): void {
  _cleanup()
}

/** 是否有音频正在播放 */
export function isPlaying(): boolean {
  return isSpeaking.value
}
