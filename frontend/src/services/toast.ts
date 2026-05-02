/**
 * 简易 Toast 通知服务（替代 ant-design-vue message）
 * 纯 DOM 操作，无框架依赖，暗色科技风格
 */

type ToastType = 'success' | 'error' | 'info' | 'warning' | 'loading'

const ICONS: Record<ToastType, string> = {
  success: '✅',
  error: '❌',
  info: 'ℹ️',
  warning: '⚠️',
  loading: '⏳',
}

const BORDER_COLORS: Record<ToastType, string> = {
  success: 'rgba(52,199,89,0.5)',
  error: 'rgba(255,77,79,0.5)',
  info: 'rgba(102,126,234,0.5)',
  warning: 'rgba(255,165,0,0.5)',
  loading: 'rgba(102,126,234,0.4)',
}

function injectStyles(): void {
  if (document.getElementById('__toast_styles__')) return
  const style = document.createElement('style')
  style.id = '__toast_styles__'
  style.textContent = `
    #__toast_container__ {
      position: fixed;
      top: 72px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 99999;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      pointer-events: none;
      min-width: 200px;
    }
    .toast-item {
      padding: 10px 20px;
      border-radius: 10px;
      background: rgba(12, 12, 24, 0.96);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(102,126,234,0.3);
      color: rgba(255,255,255,0.9);
      font-size: 14px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 200px;
      max-width: 420px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5);
      opacity: 0;
      transform: translateY(-12px) scale(0.95);
      transition: all 0.28s cubic-bezier(0.34, 1.56, 0.64, 1);
      pointer-events: none;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .toast-item.toast-visible {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
    .toast-item.toast-hiding {
      opacity: 0;
      transform: translateY(-8px) scale(0.97);
      transition: all 0.22s ease;
    }
  `
  document.head.appendChild(style)
}

function getOrCreateContainer(): HTMLElement {
  let el = document.getElementById('__toast_container__')
  if (!el) {
    injectStyles()
    el = document.createElement('div')
    el.id = '__toast_container__'
    document.body.appendChild(el)
  }
  return el
}

function showToast(type: ToastType, content: string, duration = 3000): () => void {
  const container = getOrCreateContainer()
  const el = document.createElement('div')
  el.className = 'toast-item'
  el.style.borderColor = BORDER_COLORS[type]
  el.innerHTML = `<span style="font-size:16px;flex-shrink:0">${ICONS[type]}</span><span>${content}</span>`
  container.appendChild(el)

  // trigger animation
  requestAnimationFrame(() => {
    requestAnimationFrame(() => el.classList.add('toast-visible'))
  })

  const hide = () => {
    el.classList.add('toast-hiding')
    setTimeout(() => el.remove(), 250)
  }

  let timer: ReturnType<typeof setTimeout> | null = null
  if (duration > 0) {
    timer = setTimeout(hide, duration)
  }

  return () => {
    if (timer) clearTimeout(timer)
    hide()
  }
}

// Loading toasts with key-based management
const loadingMap = new Map<string, () => void>()

export const toast = {
  success(content: string, duration = 3000): void {
    showToast('success', content, duration)
  },
  error(content: string, duration = 4000): void {
    showToast('error', content, duration)
  },
  info(content: string, duration = 3000): void {
    showToast('info', content, duration)
  },
  warning(content: string, duration = 3500): void {
    showToast('warning', content, duration)
  },
  loading(content: string, key?: string): void {
    const hide = showToast('loading', content, 0)
    if (key) loadingMap.set(key, hide)
  },
  // Dismiss a loading toast and show a follow-up
  successAfter(content: string, key?: string, duration = 3000): void {
    if (key) {
      loadingMap.get(key)?.()
      loadingMap.delete(key)
    }
    showToast('success', content, duration)
  },
  errorAfter(content: string, key?: string, duration = 4000): void {
    if (key) {
      loadingMap.get(key)?.()
      loadingMap.delete(key)
    }
    showToast('error', content, duration)
  },
  dismiss(key: string): void {
    loadingMap.get(key)?.()
    loadingMap.delete(key)
  },
}
