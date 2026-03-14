<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useToast } from '../composables/useToast'
import GraphView from '../components/GraphView.vue'
import { ingestText, getEntities, getAllEdges } from '../api'
import type { Entity, EntityEdge } from '../api'

const { t, locale } = useI18n()
const toast = useToast()
const route = useRoute()
const GROUP_ID = route.params.id as string
const THREAD_ID = crypto.randomUUID()

// 语言切换
const toggleLocale = () => {
  locale.value = locale.value === 'zh' ? 'en' : 'zh'
  localStorage.setItem('locale', locale.value)
}

const entities = ref<Entity[]>([])
const edges = ref<EntityEdge[]>([])
const input = ref('')
const isProcessing = ref(false)
const newEntityIds = ref<Set<string>>(new Set())
const fileInput = ref<HTMLInputElement | null>(null)
const isRefreshing = ref(false)
const pollingStatus = ref('')
const pollingProgress = ref(0) // 0-100
const pollingStage = ref('') // 提取阶段描述
const entitiesCount = ref(0) // 已提取实体数
const tripletsCount = ref(0) // 已提取关系数
let uploadWs: WebSocket | null = null

async function refreshGraph() {
  const [ents, edgs] = await Promise.all([
    getEntities(GROUP_ID),
    getAllEdges(GROUP_ID)
  ])
  entities.value = ents
  edges.value = edgs
}

async function manualRefresh() {
  isRefreshing.value = true
  try {
    const oldEntityCount = entities.value.length
    const oldEdgeCount = edges.value.length

    await refreshGraph()

    const newEntityCount = entities.value.length
    const newEdgeCount = edges.value.length

    if (oldEntityCount === newEntityCount && oldEdgeCount === newEdgeCount) {
      toast.info('图谱已是最新状态')
    } else {
      toast.success(`图谱已刷新 (${newEntityCount} 实体, ${newEdgeCount} 关系)`)
    }
  } catch (e: any) {
    toast.error('刷新失败: ' + e.message)
  } finally {
    isRefreshing.value = false
  }
}

// 前端验证：过滤无效输入
function isValidContent(text: string): { valid: boolean; reason?: string } {
  const trimmed = text.trim()

  // 太短
  if (trimmed.length < 10) {
    return { valid: false, reason: '内容太短，至少需要10个字符' }
  }

  // 纯数字
  if (/^\d+$/.test(trimmed)) {
    return { valid: false, reason: '请输入有意义的文本内容，而不是纯数字' }
  }

  // 重复字符
  if (/^(.)\1+$/.test(trimmed)) {
    return { valid: false, reason: '请输入有意义的文本内容' }
  }

  // 纯符号
  if (/^[^\w\s]+$/u.test(trimmed)) {
    return { valid: false, reason: '请输入有意义的文本内容' }
  }

  // 无意义词汇
  const meaningless = [
    '你好', '您好', '嗨', '谢谢', '好的', '是的', '不是', '嗯', '哦', '啊',
    'hi', 'hello', 'hey', 'thanks', 'ok', 'okay', 'yes', 'no',
    '1', '2', '3', '11', '22', '33', '111', '222', '333', '1111', '2222'
  ]
  if (meaningless.includes(trimmed.toLowerCase())) {
    return { valid: false, reason: '请输入更具体的内容' }
  }

  return { valid: true }
}

async function handleSubmit() {
  if (!input.value.trim() || isProcessing.value) return

  const content = input.value.trim()

  // 前端验证
  const validation = isValidContent(content)
  if (!validation.valid) {
    toast.warning(validation.reason || '输入内容无效')
    input.value = ''
    return
  }

  input.value = ''
  isProcessing.value = true
  pollingProgress.value = 0

  try {
    console.log('提交内容:', content)

    // 阶段1: 提交内容
    pollingStage.value = '正在提交内容'
    pollingProgress.value = 10
    const result = await ingestText(GROUP_ID, THREAD_ID, content)
    console.log('ingestText 返回:', result)

    // 阶段2: AI 分析中
    pollingStage.value = 'AI 正在分析文本'
    pollingProgress.value = 20
    toast.info('AI 正在提取实体和关系...')

    const oldIds = new Set(entities.value.map(e => e.id))

    // 轮询检查新实体（最多尝试20次，每次间隔1.5秒）
    let newIds: string[] = []
    let lastEntityCount = entities.value.length
    let noChangeCount = 0  // 连续无变化的次数
    const maxAttempts = 20
    const MAX_NO_CHANGE = 3  // 连续3次无变化则停止

    for (let i = 0; i < maxAttempts; i++) {
      // 更新进度：20% - 90% 线性增长
      const progressPercent = 20 + Math.floor((i / maxAttempts) * 70)
      pollingProgress.value = progressPercent

      // 根据进度显示不同阶段
      if (progressPercent < 40) {
        pollingStage.value = '🔍 AI 正在识别实体'
      } else if (progressPercent < 60) {
        pollingStage.value = '🔗 正在分析关系'
      } else if (progressPercent < 80) {
        pollingStage.value = '📊 正在构建图谱'
      } else {
        pollingStage.value = '✨ 即将完成'
      }

      await new Promise(resolve => setTimeout(resolve, 1500))

      // 🔥 实时获取最新数据并更新图谱
      const [ents, edgs] = await Promise.all([
        getEntities(GROUP_ID),
        getAllEdges(GROUP_ID)
      ])

      console.log(`第 ${i + 1} 次检查: 当前实体数 ${ents.length}`)

      // 检查是否有变化
      const hasChange = ents.length !== lastEntityCount

      if (hasChange) {
        // 🔥 有变化，立即更新图谱
        entities.value = ents
        edges.value = edgs
        newIds = ents.filter(e => !oldIds.has(e.id)).map(e => e.id)
        console.log(`🔄 实时更新图谱: ${ents.length} 实体, ${edgs.length} 关系`)
        lastEntityCount = ents.length
        noChangeCount = 0  // 重置无变化计数
      } else {
        // 无变化，计数器+1
        noChangeCount++
        if (noChangeCount >= MAX_NO_CHANGE) {
          console.log(`连续${MAX_NO_CHANGE}次无变化，停止轮询`)
          break
        }
      }
    }

    pollingProgress.value = 100
    pollingStage.value = ''
    pollingStatus.value = ''

    newEntityIds.value = new Set(newIds)

    if (newIds.length > 0) {
      toast.success(`✓ 提取了 ${newIds.length} 个新实体`)
    } else {
      toast.warning('未提取到新实体')
    }

    setTimeout(() => newEntityIds.value.clear(), 2000)
  } catch (e: any) {
    console.error('处理失败:', e)
    toast.error('处理失败: ' + (e.response?.data?.detail || e.message))
    pollingStage.value = ''
    pollingStatus.value = ''
  } finally {
    isProcessing.value = false
    pollingProgress.value = 0
  }
}

async function handleFileUpload(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files?.length || isProcessing.value) return

  const file = target.files[0]
  isProcessing.value = true
  pollingProgress.value = 0
  entitiesCount.value = 0
  tripletsCount.value = 0

  try {
    pollingStage.value = '📤 正在上传文件'
    pollingProgress.value = 5
    toast.info(`正在处理文件: ${file.name}`)

    const { uploadFile, connectUploadWs } = await import('../api')

    // 提交文件，获取 task_id
    console.log('开始上传文件:', file.name)
    const uploadResult = await uploadFile(GROUP_ID, THREAD_ID, file)
    console.log('上传响应:', uploadResult)

    if (!uploadResult || !uploadResult.task_id) {
      throw new Error('上传失败：未返回 task_id')
    }

    const taskId = uploadResult.task_id
    console.log('文件上传成功，task_id:', taskId)

    // 使用轮询方式获取进度（WebSocket 暂时有问题）
    const oldIds = new Set(entities.value.map(e => e.id))
    const { default: axios } = await import('axios')
    const api = axios.create({ baseURL: '/api' })

    // 智能刷新：检测到实体数变化时才刷新图谱（而不是定时轮询）
    let lastKnownEntityCount = 0
    let lastKnownTripletCount = 0

    // 轮询检查任务状态
    const pollInterval = setInterval(async () => {
      try {
        const { data: message } = await api.get(`/memory/upload/status/${taskId}`)
        console.log('任务状态:', message)

        // 更新进度信息
        // PROGRESS 状态下，stage 在 result.stage 里
        if (message.state === 'PROGRESS' && message.result) {
          pollingStage.value = message.result.stage || message.stage || '处理中'
          pollingProgress.value = message.result.progress || message.progress || 0
          entitiesCount.value = message.result.entities_count || 0
          tripletsCount.value = message.result.triplets_count || 0

          // 🔥 智能刷新：检测到数量变化时立即刷新图谱
          const currentEntityCount = message.result.entities_count || 0
          const currentTripletCount = message.result.triplets_count || 0

          if (currentEntityCount > lastKnownEntityCount || currentTripletCount > lastKnownTripletCount) {
            console.log(`🔄 检测到数据变化: 实体 ${lastKnownEntityCount}→${currentEntityCount}, 关系 ${lastKnownTripletCount}→${currentTripletCount}`)
            lastKnownEntityCount = currentEntityCount
            lastKnownTripletCount = currentTripletCount

            try {
              const [ents, edgs] = await Promise.all([
                getEntities(GROUP_ID),
                getAllEdges(GROUP_ID)
              ])
              entities.value = ents
              edges.value = edgs
              console.log(`✅ 图谱已更新: ${ents.length} 实体, ${edgs.length} 关系`)
            } catch (refreshError) {
              console.warn('图谱刷新失败:', refreshError)
            }
          }
        } else {
          pollingStage.value = message.stage || ''
          pollingProgress.value = message.progress || 0
          entitiesCount.value = message.current || 0
          tripletsCount.value = message.total || 0
        }

        // 任务完成，最终刷新图谱
        if (message.state === 'SUCCESS') {
          clearInterval(pollInterval)

          pollingStage.value = '✅ 正在更新图谱'
          pollingProgress.value = 95

          const [ents, edgs] = await Promise.all([
            getEntities(GROUP_ID),
            getAllEdges(GROUP_ID)
          ])

          entities.value = ents
          edges.value = edgs

          const newIds = ents.filter(e => !oldIds.has(e.id)).map(e => e.id)
          newEntityIds.value = new Set(newIds)

          pollingProgress.value = 100
          pollingStage.value = ''

          const result = message.result || {}
          toast.success(`✓ 处理完成：${result.entities_count || 0} 个实体，${result.triplets_count || 0} 个关系`)

          setTimeout(() => {
            newEntityIds.value.clear()
            entitiesCount.value = 0
            tripletsCount.value = 0
            isProcessing.value = false
          }, 3000)
        } else if (message.state === 'FAILURE') {
          clearInterval(pollInterval)
          throw new Error(message.error || '处理失败')
        }
      } catch (pollError) {
        console.error('轮询错误:', pollError)
        clearInterval(pollInterval)
        throw pollError
      }
    }, 1000) // 每秒轮询一次
  } catch (e: any) {
    console.error('文件上传失败:', e)
    toast.error('文件处理失败: ' + (e.response?.data?.detail || e.message))
    pollingStage.value = ''
    entitiesCount.value = 0
    tripletsCount.value = 0
    isProcessing.value = false
  } finally {
    pollingProgress.value = 0
    target.value = ''
  }
}

async function testConnection() {
  try {
    await fetch('/api/health')
    console.log('✓ 后端连接正常')
  } catch (e) {
    console.error('✗ 后端连接失败:', e)
    toast.error('无法连接到后端，请确保后端服务已启动')
  }
}

onMounted(async () => {
  await testConnection()
  await refreshGraph()
})
</script>

<template>
  <div class="live-builder">
    <div class="graph-panel">
      <div class="panel-header">
        <h2>{{ $t('graph.title') }}</h2>
        <div class="header-actions">
          <div class="stats">
            <span>{{ entities.length }} {{ $t('common.entity') }}</span>
            <span>{{ edges.length }} {{ $t('common.relation') }}</span>
          </div>
          <button
            class="lang-btn"
            @click="toggleLocale"
            :title="locale === 'zh' ? 'Switch to English' : '切换到中文'"
          >
            {{ locale === 'zh' ? 'EN' : '中' }}
          </button>
          <button
            class="refresh-btn"
            @click="manualRefresh"
            :disabled="isRefreshing"
            :title="$t('common.refresh')"
          >
            <svg :class="{ spinning: isRefreshing }" width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M13.65 2.35A7 7 0 103 10h2a5 5 0 1110-2.62L13 5v4h4l-3.35-6.65z" fill="currentColor"/>
            </svg>
          </button>
        </div>
      </div>
      <div class="graph-container">
        <GraphView :entities="entities" :edges="edges" :processing="isProcessing" />

        <!-- 实时分析中的提示 -->
        <div v-if="isProcessing && entities.length > 0" class="realtime-indicator">
          <div class="indicator-content">
            <!-- 多层旋转圆环图标 -->
            <div class="spinner-rings">
              <svg width="20" height="20" viewBox="0 0 20 20" class="ring-outer">
                <circle cx="10" cy="10" r="8" fill="none" stroke="white" stroke-width="2"
                        stroke-dasharray="15 35" stroke-linecap="round" opacity="0.6"/>
              </svg>
              <svg width="20" height="20" viewBox="0 0 20 20" class="ring-inner">
                <circle cx="10" cy="10" r="5" fill="none" stroke="white" stroke-width="2"
                        stroke-dasharray="8 22" stroke-linecap="round" opacity="0.8"/>
              </svg>
              <div class="ring-center"></div>
            </div>
            <span class="indicator-text">{{ $t('graph.realtimeAnalysis') }}</span>
            <span v-if="entitiesCount > 0" class="indicator-stats">
              {{ entitiesCount }} {{ $t('common.entity') }} · {{ tripletsCount }} {{ $t('common.relation') }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="control-panel">
      <div class="input-area">
        <textarea
          v-model="input"
          placeholder="输入文本或粘贴内容，按 Cmd/Ctrl + Enter 提交..."
          @keydown.meta.enter="handleSubmit"
          @keydown.ctrl.enter="handleSubmit"
          :disabled="isProcessing"
        ></textarea>
      </div>

      <div class="action-area">
        <div class="status-bar">
          <!-- 进度条 -->
          <div v-if="isProcessing && pollingProgress > 0" class="progress-container">
            <div class="progress-info">
              <span class="progress-stage">{{ pollingStage }}</span>
              <span class="progress-percent">{{ pollingProgress }}%</span>
            </div>
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: pollingProgress + '%' }"
              ></div>
            </div>
            <!-- 实时统计 -->
            <div v-if="entitiesCount > 0 || tripletsCount > 0" class="progress-stats">
              <span class="stat-item">
                <span class="stat-icon">🔷</span>
                <span class="stat-value">{{ entitiesCount }}</span>
                <span class="stat-label">实体</span>
              </span>
              <span class="stat-divider">·</span>
              <span class="stat-item">
                <span class="stat-icon">🔗</span>
                <span class="stat-value">{{ tripletsCount }}</span>
                <span class="stat-label">关系</span>
              </span>
            </div>
          </div>
          <!-- 状态文本 -->
          <div v-else class="status-text-container">
            <span v-if="pollingStatus" class="status-text">{{ pollingStatus }}</span>
            <span v-else-if="isProcessing" class="status-text processing">处理中...</span>
            <span v-else class="status-text ready">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5"/>
                <path d="M5 7l1.5 1.5L10 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              就绪
            </span>
          </div>
        </div>

        <div class="buttons">
          <button
            class="upload-btn"
            :disabled="isProcessing"
            @click="fileInput?.click()"
            title="上传文件"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M6 14l4-4 4 4M10 10v8M17 10a7 7 0 10-14 0" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
          </button>
          <button
            v-ripple
            class="submit-btn"
            :disabled="!input.trim() || isProcessing"
            @click="handleSubmit"
          >
            <span v-if="!isProcessing">提取实体</span>
            <div v-else class="btn-spinner"></div>
          </button>
        </div>

        <input
          ref="fileInput"
          type="file"
          accept=".pdf,.txt,.md"
          @change="handleFileUpload"
          style="display: none"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.live-builder {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg-page);
}

.graph-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: var(--space-6);
  padding-bottom: 0;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);
}

.panel-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.stats {
  display: flex;
  gap: var(--space-4);
  font-size: 13px;
  color: var(--text-tertiary);
}

.refresh-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--primary);
  border-color: var(--primary);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-btn svg.spinning {
  animation: spin 1s linear infinite;
}

.lang-btn {
  width: 36px;
  height: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.lang-btn:hover {
  background: var(--bg-hover);
  color: var(--primary);
  border-color: var(--primary);
}

.graph-container {
  flex: 1;
  background: var(--bg-white);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  position: relative;
}

/* 实时分析指示器 */
.realtime-indicator {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  pointer-events: none;
}

.indicator-content {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.95), rgba(139, 92, 246, 0.95));
  background-size: 200% 200%;
  animation: slideDown 0.3s ease, gradientShift 3s ease infinite;
  backdrop-filter: blur(8px);
  border-radius: var(--radius-full);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
  color: white;
  font-size: 13px;
  font-weight: 600;
}

@keyframes gradientShift {
  0%, 100% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
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

/* 多层旋转圆环 */
.spinner-rings {
  position: relative;
  width: 20px;
  height: 20px;
}

.ring-outer {
  position: absolute;
  top: 0;
  left: 0;
  animation: spinClockwise 2s linear infinite;
}

.ring-inner {
  position: absolute;
  top: 0;
  left: 0;
  animation: spinCounterClockwise 1.5s linear infinite;
}

.ring-center {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 4px;
  height: 4px;
  background: white;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  animation: glow 1.5s ease-in-out infinite;
}

@keyframes spinClockwise {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@keyframes spinCounterClockwise {
  from {
    transform: rotate(360deg);
  }
  to {
    transform: rotate(0deg);
  }
}

@keyframes glow {
  0%, 100% {
    opacity: 1;
    box-shadow: 0 0 4px white;
  }
  50% {
    opacity: 0.7;
    box-shadow: 0 0 8px white, 0 0 12px rgba(255, 255, 255, 0.5);
  }
}

.indicator-text {
  font-weight: 600;
}

.indicator-stats {
  font-weight: 500;
  opacity: 0.9;
  padding-left: 8px;
  border-left: 1px solid rgba(255, 255, 255, 0.3);
}

.control-panel {
  min-height: 140px;
  background: var(--bg-white);
  border-top: 1px solid var(--border-secondary);
  display: flex;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-6);
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
}

.input-area {
  flex: 1;
  display: flex;
}

.input-area textarea {
  width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  font-family: var(--font-sans);
}

.input-area textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}

.action-area {
  width: 200px;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.status-bar {
  padding: var(--space-3);
  background: var(--gray-50);
  border-radius: var(--radius-md);
  min-height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 进度条容器 */
.progress-container {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.progress-stage {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary);
  display: flex;
  align-items: center;
  gap: 4px;
}

.progress-percent {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-quaternary);
  font-family: var(--font-mono);
}

.progress-bar {
  width: 100%;
  height: 6px;
  background: var(--gray-200);
  border-radius: var(--radius-full);
  overflow: hidden;
  position: relative;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary) 0%, #8b5cf6 100%);
  border-radius: var(--radius-full);
  transition: width 0.3s ease;
  position: relative;
  overflow: hidden;
}

.progress-fill::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.3) 50%,
    transparent 100%
  );
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.progress-stats {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.stat-icon {
  font-size: 14px;
}

.stat-value {
  font-weight: 700;
  color: var(--primary);
  font-family: var(--font-mono);
}

.stat-label {
  color: var(--text-tertiary);
}

.stat-divider {
  color: var(--border-primary);
  margin: 0 4px;
}

/* 状态文本 */
.status-text-container {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}

.status-text {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.status-text.processing {
  color: var(--warning);
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-text.processing::before {
  content: '';
  width: 8px;
  height: 8px;
  background: var(--warning);
  border-radius: 50%;
  animation: pulse-dot 1.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.2); }
}

.status-text.ready {
  color: var(--success);
  display: flex;
  align-items: center;
  gap: 6px;
}

.buttons {
  flex: 1;
  display: flex;
  gap: var(--space-2);
}

.submit-btn {
  flex: 1;
  padding: var(--space-3);
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.submit-btn:hover:not(:disabled) {
  background: var(--primary-hover);
  box-shadow: var(--shadow-sm);
}

.submit-btn:disabled {
  background: var(--gray-300);
  cursor: not-allowed;
}

.upload-btn {
  width: 56px;
  padding: 0;
  background: var(--bg-white);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  transition: all var(--transition-fast);
}

.upload-btn:hover:not(:disabled) {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-light);
}

.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
