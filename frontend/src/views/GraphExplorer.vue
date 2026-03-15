<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getEntities, getAllEdges, ingestText } from '../api'
import { useToast } from '../composables/useToast'
import GraphView from '../components/GraphView.vue'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const GROUP_ID = route.params.id as string
const THREAD_ID = crypto.randomUUID()

const entities = ref<any[]>([])
const edges = ref<any[]>([])
const isLoading = ref(true)
const searchQuery = ref('')
const showSources = ref(false)  // 默认隐藏空的来源面板
const chatInput = ref('')
const isProcessing = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const processingStatus = ref('')
const processingProgress = ref(0)
let refreshInterval: number | null = null
let uploadWs: WebSocket | null = null

// 搜索过滤
const filteredEntities = computed(() => {
  if (!searchQuery.value.trim()) return entities.value
  const query = searchQuery.value.toLowerCase()
  return entities.value.filter(e =>
    e.name.toLowerCase().includes(query) ||
    (e.display_name && e.display_name.toLowerCase().includes(query))
  )
})

const filteredEdges = computed(() => {
  if (!searchQuery.value.trim()) return edges.value
  const allowedIds = new Set(filteredEntities.value.map(e => e.id))
  return edges.value.filter(e =>
    allowedIds.has(e.source_entity_id) && allowedIds.has(e.target_entity_id)
  )
})

const hasSearchResults = computed(() => {
  if (!searchQuery.value.trim()) return true
  return filteredEntities.value.length > 0
})

const isEmpty = computed(() => {
  return !isLoading.value && entities.value.length === 0
})

function clearSearch() {
  searchQuery.value = ''
}

async function loadData() {
  try {
    const [ents, edgs] = await Promise.all([
      getEntities(GROUP_ID),
      getAllEdges(GROUP_ID)
    ])
    entities.value = ents
    edges.value = edgs
  } catch (e) {
    console.error(e)
    toast.error('加载数据失败')
  } finally {
    isLoading.value = false
  }
}

async function handleChatSubmit() {
  if (!chatInput.value.trim() || isProcessing.value) return

  const text = chatInput.value.trim()
  const oldCount = entities.value.length
  isProcessing.value = true

  try {
    toast.info('正在提取实体...')
    await ingestText(GROUP_ID, THREAD_ID, text)

    const [ents, edgs] = await Promise.all([
      getEntities(GROUP_ID),
      getAllEdges(GROUP_ID)
    ])
    entities.value = ents
    edges.value = edgs

    const newCount = ents.length - oldCount
    chatInput.value = ''
    toast.success(`✓ 提取完成，新增 ${newCount} 个实体`)
  } catch (e: any) {
    console.error(e)
    let errorMsg = '提取失败'
    const status = e.response?.status

    if (status === 400) {
      errorMsg = '输入文本格式错误，请检查后重试'
    } else if (status === 500) {
      errorMsg = 'AI 处理失败，请稍后重试或联系管理员'
    } else if (e.response?.data?.detail) {
      errorMsg = e.response.data.detail
    }

    toast.error(`✗ ${errorMsg}`)
  } finally {
    isProcessing.value = false
  }
}

function startAutoRefresh() {
  // 每3秒自动刷新一次数据
  if (refreshInterval) clearInterval(refreshInterval)
  refreshInterval = window.setInterval(async () => {
    try {
      const [ents, edgs] = await Promise.all([
        getEntities(GROUP_ID),
        getAllEdges(GROUP_ID)
      ])
      entities.value = ents
      edges.value = edgs
    } catch (e) {
      console.error('自动刷新失败:', e)
    }
  }, 3000)
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

async function handleFileUpload(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files?.length || isProcessing.value) return

  const file = target.files[0]
  const oldCount = entities.value.length
  isProcessing.value = true
  processingProgress.value = 0

  try {
    toast.info(`📤 正在上传 ${file.name}...`)
    const { uploadFile, connectUploadWs } = await import('../api')
    const response = await uploadFile(GROUP_ID, THREAD_ID, file)

    const taskId = response.task_id
    processingStatus.value = '正在解析文档...'

    // 建立 WebSocket 连接监听进度
    uploadWs = connectUploadWs(
      taskId,
      (data) => {
        console.log('收到进度更新:', data)
        if (data.state === 'PROGRESS') {
          processingStatus.value = data.stage || '处理中...'
          processingProgress.value = data.progress || 0
        } else if (data.state === 'SUCCESS') {
          processingStatus.value = '处理完成'
          processingProgress.value = 100
          stopAutoRefresh()
          uploadWs?.close()

          // 最后刷新一次
          loadData().then(() => {
            const newCount = entities.value.length - oldCount
            toast.success(`✓ 文件处理完成，新增 ${newCount} 个实体`)
            isProcessing.value = false
          })
        } else if (data.state === 'FAILURE') {
          stopAutoRefresh()
          uploadWs?.close()
          toast.error(`✗ 处理失败: ${data.error || '未知错误'}`)
          isProcessing.value = false
        }
      },
      () => {
        // WebSocket 关闭
        stopAutoRefresh()
      }
    )

    // 开始自动刷新数据
    startAutoRefresh()

  } catch (e: any) {
    console.error(e)
    stopAutoRefresh()
    let errorMsg = '上传失败'
    const status = e.response?.status

    if (status === 413) {
      errorMsg = '文件过大，请选择小于 10MB 的文件'
    } else if (status === 400) {
      errorMsg = '文件格式不支持，请上传 PDF、TXT 或 MD 文件'
    } else if (status === 500) {
      errorMsg = '服务器处理失败，请稍后重试'
    } else if (e.response?.data?.detail) {
      errorMsg = e.response.data.detail
    }

    toast.error(`✗ ${errorMsg}`)
    isProcessing.value = false
  } finally {
    target.value = ''
  }
}

onMounted(loadData)

onUnmounted(() => {
  stopAutoRefresh()
  if (uploadWs) {
    uploadWs.close()
    uploadWs = null
  }
})
</script>

<template>
  <div class="notebook-explorer">
    <!-- 顶部导航栏 -->
    <header class="top-bar">
      <div class="top-left">
        <button class="btn-back" @click="router.push('/projects')" title="返回">
          <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m15 18-6-6 6-6"/>
          </svg>
        </button>
        <nav class="breadcrumb">
          <span @click="router.push('/')">首页</span>
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
          <span @click="router.push('/projects')">项目</span>
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
          <span class="active">知识图谱</span>
        </nav>
      </div>

      <div class="top-center">
        <div class="search-box">
          <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          <input v-model="searchQuery" placeholder="搜索实体或关系" />
          <button v-if="searchQuery" class="btn-clear" @click="clearSearch" title="清除搜索">
            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <div class="top-right">
        <div class="stats">
          <span>{{ filteredEntities.length }} 实体</span>
          <span>{{ filteredEdges.length }} 关系</span>
        </div>
        <button class="btn-lang">EN</button>
      </div>
    </header>

    <!-- 处理进度条 -->
    <div v-if="isProcessing && processingProgress > 0" class="progress-bar">
      <div class="progress-info">
        <span class="progress-text">{{ processingStatus }}</span>
        <span class="progress-percent">{{ processingProgress }}%</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" :style="{ width: processingProgress + '%' }"></div>
      </div>
    </div>

    <div class="main-content">
      <!-- 左侧来源面板 -->
      <aside v-if="showSources" class="sources-panel">
        <div class="panel-header">
          <button class="btn-toggle" @click="showSources = false">
            <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg>
          </button>
          <div class="panel-title">
            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <path d="M13 2v6h6"/>
            </svg>
            <span>来源</span>
            <span class="count">0</span>
          </div>
          <button class="btn-filter">
            <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/></svg>
          </button>
        </div>

        <div class="sources-list">
          <div class="empty">
            <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
              <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <path d="M13 2v6h6"/>
            </svg>
            <p>暂无数据源</p>
          </div>
        </div>
      </aside>

      <!-- 中间画布区域 -->
      <main class="canvas-area">
        <div class="canvas-wrapper">
          <!-- 骨架屏 -->
          <div v-if="isLoading" class="skeleton-screen">
            <div class="skeleton-nodes">
              <div v-for="i in 8" :key="i" class="skeleton-node" :style="{
                left: Math.random() * 80 + 10 + '%',
                top: Math.random() * 80 + 10 + '%'
              }"></div>
            </div>
            <p>加载中...</p>
          </div>

          <!-- 空状态 -->
          <div v-else-if="isEmpty" class="empty-state">
            <svg width="64" height="64" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
              <circle cx="32" cy="32" r="28"/>
              <circle cx="22" cy="28" r="4"/>
              <circle cx="42" cy="28" r="4"/>
              <circle cx="32" cy="42" r="4"/>
              <line x1="22" y1="28" x2="32" y2="42"/>
              <line x1="42" y1="28" x2="32" y2="42"/>
            </svg>
            <h3>开始构建知识图谱</h3>
            <p>在下方输入文本或上传文档，系统将自动提取实体和关系</p>
          </div>

          <!-- 搜索无结果 -->
          <div v-else-if="!hasSearchResults" class="empty-state">
            <svg width="64" height="64" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
              <circle cx="32" cy="28" r="18"/>
              <line x1="44" y1="40" x2="54" y2="50"/>
              <line x1="22" y1="22" x2="42" y2="34"/>
            </svg>
            <h3>未找到匹配结果</h3>
            <p>尝试使用其他关键词搜索</p>
          </div>

          <!-- 图谱 -->
          <div v-else class="graph-container">
            <GraphView
              :entities="filteredEntities"
              :edges="filteredEdges"
              :loading="isLoading"
            />

            <!-- 处理中遮罩 -->
            <div v-if="isProcessing" class="processing-overlay">
              <div class="processing-indicator">
                <div class="spinner"></div>
                <p>实时渲染中...</p>
              </div>
            </div>
          </div>

          <!-- 展开按钮 -->
          <button v-if="!showSources" class="btn-expand" @click="showSources = true">
            <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
          </button>
        </div>

        <!-- 底部输入区 -->
        <div class="input-bar">
          <div class="input-container">
            <textarea
              v-model="chatInput"
              placeholder="输入文本添加到知识图谱，按 Cmd/Ctrl + Enter 提交..."
              :disabled="isProcessing"
              @keydown.enter="(e) => {
                if ((e.metaKey || e.ctrlKey) && !e.shiftKey) {
                  e.preventDefault()
                  handleChatSubmit()
                }
              }"
            ></textarea>
            <div class="input-actions">
              <button class="btn-action btn-upload" :disabled="isProcessing" @click="fileInput?.click()" title="上传文件 (PDF, TXT, MD)">
                <svg v-if="!isProcessing" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                </svg>
                <svg v-else class="spinner" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="9" cy="9" r="8" opacity="0.25"/>
                  <path d="M9 1a8 8 0 018 8" stroke-linecap="round"/>
                </svg>
              </button>
              <button class="btn-action btn-submit" :disabled="!chatInput.trim() || isProcessing" @click="handleChatSubmit">
                <svg v-if="isProcessing" class="spinner" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="8" cy="8" r="7" opacity="0.25"/>
                  <path d="M8 1a7 7 0 017 7" stroke-linecap="round"/>
                </svg>
                <span v-if="isProcessing">处理中</span>
                <span v-else>提交</span>
              </button>
            </div>
          </div>
          <input ref="fileInput" type="file" accept=".pdf,.txt,.md" @change="handleFileUpload" style="display: none" />
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.notebook-explorer {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f8f9fa;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ===== 顶部栏 ===== */
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 20px;
  background: white;
  border-bottom: 1px solid #e8eaed;
  gap: 20px;
  flex-shrink: 0;
  box-shadow: 0 1px 3px rgba(60, 64, 67, 0.08);
}

.top-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.btn-back {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #dadce0;
  background: white;
  border-radius: 8px;
  color: #5f6368;
  cursor: pointer;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
}

.btn-back:hover {
  background: #f8f9fa;
  border-color: #dadce0;
  color: #202124;
  box-shadow: 0 1px 3px 0 rgba(60, 64, 67, 0.3), 0 4px 8px 3px rgba(60, 64, 67, 0.15);
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #5f6368;
  font-weight: 500;
}

.breadcrumb span {
  cursor: pointer;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
  padding: 4px 8px;
  border-radius: 12px;
}

.breadcrumb span:hover:not(.active) {
  color: #1a73e8;
  background: rgba(26, 115, 232, 0.08);
}

.breadcrumb span.active {
  color: #202124;
  font-weight: 600;
}

.breadcrumb svg {
  width: 12px;
  height: 12px;
  color: #dadce0;
  flex-shrink: 0;
}

.top-center {
  flex: 0 0 400px;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  height: 40px;
  background: white;
  border: 1px solid #dadce0;
  border-radius: 24px;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
}

.search-box:hover {
  box-shadow: 0 1px 3px 0 rgba(60, 64, 67, 0.3), 0 4px 8px 3px rgba(60, 64, 67, 0.15);
}

.search-box:focus-within {
  background: white;
  border-color: #1a73e8;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 6px 2px rgba(26, 115, 232, 0.3);
}

.search-box input:focus {
  outline: none;
}

.search-box svg {
  flex-shrink: 0;
  color: #9ca3af;
}

.search-box input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 14px;
  color: #111827;
}

.search-box input::placeholder {
  color: #9ca3af;
}

.btn-clear {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 50%;
  color: #80868b;
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.btn-clear:hover {
  background: #f1f3f4;
  color: #202124;
}

.btn-clear svg {
  width: 14px;
  height: 14px;
}

.top-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stats {
  display: flex;
  gap: 12px;
  font-size: 13px;
  color: #5f6368;
  font-weight: 500;
}

.stats span {
  padding: 6px 12px;
  background: white;
  border: 1px solid #dadce0;
  border-radius: 16px;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.stats span:hover {
  box-shadow: 0 1px 3px 0 rgba(60, 64, 67, 0.3), 0 4px 8px 3px rgba(60, 64, 67, 0.15);
}

.btn-lang {
  padding: 6px 12px;
  border: 1px solid #dadce0;
  background: white;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 500;
  color: #5f6368;
  cursor: pointer;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
}

.btn-lang:hover {
  border-color: #dadce0;
  color: #202124;
  box-shadow: 0 1px 3px 0 rgba(60, 64, 67, 0.3), 0 4px 8px 3px rgba(60, 64, 67, 0.15);
}

/* ===== 主内容区 ===== */
.main-content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ===== 左侧来源面板 ===== */
.sources-panel {
  width: 380px;
  background: #fafbfc;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid #e5e7eb;
  background: white;
}

.btn-toggle {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 8px;
  color: #5f6368;
  cursor: pointer;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.btn-toggle:hover {
  background: #f1f3f4;
  color: #202124;
}

.panel-title {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: #202124;
}

.panel-title svg {
  color: #5f6368;
  width: 16px;
  height: 16px;
}

.count {
  padding: 2px 8px;
  background: #f1f3f4;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  color: #5f6368;
  line-height: 1.5;
}

.btn-filter {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 8px;
  color: #5f6368;
  cursor: pointer;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.btn-filter:hover {
  background: #f1f3f4;
  color: #202124;
}

.sources-list {
  flex: 1;
  overflow-y: auto;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.sources-list::-webkit-scrollbar {
  width: 8px;
}

.sources-list::-webkit-scrollbar-track {
  background: transparent;
}

.sources-list::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 4px;
}

.sources-list::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #9ca3af;
  font-size: 14px;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex: 1;
  color: #80868b;
  font-size: 13px;
  padding: 32px 20px;
  text-align: center;
}

.empty svg {
  opacity: 0.3;
  color: #80868b;
}

.empty p {
  margin: 0;
  font-weight: 400;
  color: #5f6368;
}

.source-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  margin-bottom: 8px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.source-item:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
}

.source-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.source-content {
  flex: 1;
  min-width: 0;
}

.source-text {
  font-size: 13px;
  line-height: 1.5;
  color: #111827;
  margin: 0 0 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.source-date {
  font-size: 11px;
  color: #9ca3af;
}

/* ===== 中间画布 ===== */
.canvas-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.canvas-wrapper {
  flex: 1;
  position: relative;
  background: linear-gradient(to bottom, #fafbfc 0%, #ffffff 100%);
  overflow: hidden;
  min-height: 0;
  max-height: 100%;
}

.canvas-wrapper > .skeleton-screen,
.canvas-wrapper > .graph-container {
  width: 100%;
  height: 100%;
  position: absolute;
  top: 0;
  left: 0;
}

.graph-container {
  display: block;
}

.graph-container :deep(> *) {
  width: 100%;
  height: 100%;
}

.skeleton-screen {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  background: #fafbfc;
}

.skeleton-nodes {
  position: relative;
  width: 400px;
  height: 300px;
}

.skeleton-node {
  position: absolute;
  width: 40px;
  height: 40px;
  background: linear-gradient(90deg, #e5e7eb 25%, #d1d5db 50%, #e5e7eb 75%);
  background-size: 200% 100%;
  border-radius: 50%;
  animation: shimmer 1.5s ease-in-out infinite;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

@keyframes shimmer {
  0% { background-position: -100% 0; }
  100% { background-position: 100% 0; }
}

.skeleton-screen p {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.skeleton-screen > p {
  color: #9ca3af;
  font-size: 14px;
  font-weight: 500;
  margin: 0;
}

.btn-expand {
  position: absolute;
  top: 16px;
  left: 16px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: white;
  border: 1px solid #dadce0;
  border-radius: 8px;
  color: #5f6368;
  cursor: pointer;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 10;
}

.btn-expand:hover {
  background: #f8f9fa;
  border-color: #dadce0;
  color: #202124;
  box-shadow: 0 1px 3px 0 rgba(60, 64, 67, 0.3), 0 4px 8px 3px rgba(60, 64, 67, 0.15);
}

/* ===== 处理进度条 ===== */
.progress-bar {
  padding: 16px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  flex-shrink: 0;
  animation: slideDown 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 13px;
}

.progress-text {
  color: white;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress-text::before {
  content: '⚡';
  font-size: 16px;
}

.progress-percent {
  color: rgba(255, 255, 255, 0.9);
  font-weight: 600;
  font-size: 14px;
}

.progress-track {
  height: 4px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: white;
  border-radius: 2px;
  transition: width 300ms cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 0 10px rgba(255, 255, 255, 0.5);
}

/* ===== 底部输入栏 ===== */
.input-bar {
  padding: 16px 20px;
  background: white;
  border-top: 1px solid #e8eaed;
  flex-shrink: 0;
  min-height: 0;
  box-shadow: 0 -1px 3px rgba(60, 64, 67, 0.08);
}

.input-container {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  max-width: 100%;
  margin: 0;
}

.input-container textarea {
  flex: 1;
  height: 36px;
  max-height: 100px;
  padding: 8px 12px;
  border: 1px solid #dadce0;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  font-family: inherit;
  background: white;
  color: #202124;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
  overflow-y: auto;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
}

.input-container textarea:focus {
  outline: none;
  background: white;
  border-color: #1a73e8;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 6px 2px rgba(26, 115, 232, 0.3);
}

.input-container textarea:disabled {
  background: #f8f9fa;
  color: #80868b;
  cursor: not-allowed;
  border-color: #e8eaed;
}

.input-container textarea::placeholder {
  color: #80868b;
}

.input-actions {
  display: flex;
  gap: 8px;
}

.btn-action {
  height: 36px;
  padding: 0 12px;
  border: none;
  border-radius: 18px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 200ms cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.btn-upload {
  min-width: 36px;
  background: white;
  border: 1px solid #dadce0;
  color: #5f6368;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
}

.btn-upload:hover:not(:disabled) {
  background: #f8f9fa;
  border-color: #dadce0;
  color: #202124;
  box-shadow: 0 1px 3px 0 rgba(60, 64, 67, 0.3), 0 4px 8px 3px rgba(60, 64, 67, 0.15);
}

.btn-upload svg {
  width: 18px;
  height: 18px;
}

.btn-submit {
  min-width: 60px;
  background: #1a73e8;
  color: white;
  box-shadow: 0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15);
  border: none;
}

.btn-submit:hover:not(:disabled) {
  background: #1765cc;
  box-shadow: 0 1px 3px 0 rgba(60, 64, 67, 0.3), 0 4px 8px 3px rgba(60, 64, 67, 0.15);
}

.btn-upload:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #f8f9fa;
  border-color: #e8eaed;
}

.btn-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #80868b;
}

/* ===== 空状态 ===== */
.empty-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding: 40px;
  text-align: center;
  background: linear-gradient(to bottom, #fafbfc 0%, #ffffff 100%);
}

.empty-state svg {
  color: #667eea;
  opacity: 0.6;
}

.empty-state h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #202124;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
  color: #5f6368;
  max-width: 400px;
  line-height: 1.6;
}

/* ===== 处理中遮罩 ===== */
.processing-overlay {
  position: absolute;
  bottom: 20px;
  right: 20px;
  z-index: 100;
  pointer-events: none;
}

.processing-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 18px;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.95) 0%, rgba(118, 75, 162, 0.95) 100%);
  border-radius: 20px;
  box-shadow: 0 4px 20px rgba(102, 126, 234, 0.4);
  backdrop-filter: blur(10px);
  animation: fadeIn 300ms cubic-bezier(0.4, 0, 0.2, 1), pulse 2s ease-in-out infinite;
}

.processing-indicator p {
  margin: 0;
  font-size: 13px;
  color: white;
  font-weight: 500;
}

@keyframes pulse {
  0%, 100% {
    box-shadow: 0 4px 20px rgba(102, 126, 234, 0.4);
  }
  50% {
    box-shadow: 0 4px 30px rgba(102, 126, 234, 0.6);
  }
}

/* ===== Loading 动画 ===== */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.processing-indicator .spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
</style>
