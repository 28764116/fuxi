<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
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
const showSources = ref(true)
const chatInput = ref('')
const isProcessing = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

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

async function handleFileUpload(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files?.length || isProcessing.value) return

  const file = target.files[0]
  const oldCount = entities.value.length
  isProcessing.value = true

  try {
    toast.info(`📤 正在上传 ${file.name}...`)
    const { uploadFile } = await import('../api')
    await uploadFile(GROUP_ID, THREAD_ID, file)

    const [ents, edgs] = await Promise.all([
      getEntities(GROUP_ID),
      getAllEdges(GROUP_ID)
    ])
    entities.value = ents
    edges.value = edgs

    const newCount = ents.length - oldCount
    toast.success(`✓ 文件处理完成，新增 ${newCount} 个实体`)
  } catch (e: any) {
    console.error(e)
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
  } finally {
    isProcessing.value = false
    target.value = ''
  }
}

onMounted(loadData)
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

          <!-- 图谱 -->
          <div v-else class="graph-container">
            <GraphView
              :entities="filteredEntities"
              :edges="filteredEdges"
              :loading="isLoading"
            />
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
              <button class="btn-action btn-upload" :disabled="isProcessing" @click="fileInput?.click()" title="上传文件">
                <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                </svg>
              </button>
              <button class="btn-action btn-submit" :disabled="!chatInput.trim() || isProcessing" @click="handleChatSubmit">
                <span v-if="isProcessing">处理中...</span>
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
  height: 52px;
  padding: 0 16px;
  background: #fafbfc;
  border-bottom: 1px solid #e5e7eb;
  gap: 20px;
  flex-shrink: 0;
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
  border: 1px solid #e5e7eb;
  background: white;
  border-radius: 6px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-back:hover {
  background: #f9fafb;
  border-color: #d1d5db;
  color: #111827;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #6b7280;
  font-weight: 500;
}

.breadcrumb span {
  cursor: pointer;
  transition: all 0.2s;
  padding: 2px 4px;
  border-radius: 4px;
}

.breadcrumb span:hover:not(.active) {
  color: #3b82f6;
  background: rgba(59, 130, 246, 0.08);
}

.breadcrumb span.active {
  color: #111827;
  font-weight: 600;
}

.breadcrumb svg {
  width: 12px;
  height: 12px;
  color: #cbd5e1;
  flex-shrink: 0;
}

.top-center {
  flex: 0 0 400px;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  height: 36px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  transition: all 0.2s;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.search-box:focus-within {
  background: white;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12);
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

.top-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stats {
  display: flex;
  gap: 12px;
  font-size: 13px;
  color: #6b7280;
  font-weight: 600;
}

.stats span {
  padding: 4px 10px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.btn-lang {
  padding: 6px 12px;
  border: 1px solid #e5e7eb;
  background: white;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-lang:hover {
  border-color: #d1d5db;
  color: #111827;
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
  border-radius: 6px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-toggle:hover {
  background: #f3f4f6;
  color: #111827;
}

.panel-title {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.panel-title svg {
  color: #6b7280;
  width: 16px;
  height: 16px;
}

.count {
  padding: 1px 7px;
  background: #f3f4f6;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
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
  border-radius: 6px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-filter:hover {
  background: #f3f4f6;
  color: #111827;
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
  gap: 10px;
  flex: 1;
  color: #9ca3af;
  font-size: 13px;
  padding: 32px 20px;
  text-align: center;
}

.empty svg {
  opacity: 0.4;
}

.empty p {
  margin: 0;
  font-weight: 500;
  color: #6b7280;
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
  background: #ffffff;
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
  border: 1px solid #d1d5db;
  border-radius: 6px;
  color: #6b7280;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
  transition: all 0.2s;
  z-index: 10;
}

.btn-expand:hover {
  background: #f9fafb;
  border-color: #9ca3af;
  color: #111827;
  box-shadow: 0 3px 6px rgba(0, 0, 0, 0.12);
}

/* ===== 底部输入栏 ===== */
.input-bar {
  padding: 12px 20px;
  background: #fafbfc;
  border-top: 1px solid #e5e7eb;
  flex-shrink: 0;
  min-height: 0;
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
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  font-family: inherit;
  background: white;
  color: #111827;
  transition: all 0.2s;
  overflow-y: auto;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.input-container textarea:focus {
  outline: none;
  background: white;
  border-color: #9ca3af;
  box-shadow: 0 0 0 2px rgba(156, 163, 175, 0.15);
}

.input-container textarea:disabled {
  background: #f9fafb;
  color: #9ca3af;
  cursor: not-allowed;
  border-color: #e5e7eb;
}

.input-container textarea::placeholder {
  color: #9ca3af;
}

.input-actions {
  display: flex;
  gap: 8px;
}

.btn-action {
  height: 36px;
  padding: 0 12px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.btn-upload {
  min-width: 36px;
  background: white;
  border: 1px solid #d1d5db;
  color: #6b7280;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.btn-upload:hover:not(:disabled) {
  background: #f9fafb;
  border-color: #9ca3af;
  color: #111827;
}

.btn-upload svg {
  width: 18px;
  height: 18px;
}

.btn-submit {
  min-width: 60px;
  background: #111827;
  color: white;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.btn-submit:hover:not(:disabled) {
  background: #1f2937;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
}

.btn-upload:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #f3f4f6;
  border-color: #e5e7eb;
}

.btn-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: #9ca3af;
}
</style>
