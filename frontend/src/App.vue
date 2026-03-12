<script setup lang="ts">
import { ref, reactive } from 'vue'
import GraphView from './components/GraphView.vue'
import { uploadFile, getEntities, getAllEdges, ingestText } from './api'
import type { Entity, EntityEdge, Episode } from './api'

const GROUP_ID = 'test-group'
const THREAD_ID = '22222222-2222-2222-2222-222222222222'

const entities = ref<Entity[]>([])
const edges = ref<EntityEdge[]>([])
const episodes = ref<Episode[]>([])

const textInput = ref('')
const loading = ref(false)
const status = ref('')
const pollTimer = ref<number | null>(null)

async function refreshGraph() {
  status.value = '正在加载图谱...'
  try {
    entities.value = await getEntities(GROUP_ID)
    edges.value = await getAllEdges(GROUP_ID)
    status.value = `图谱已加载: ${entities.value.length} 个实体, ${edges.value.filter(e => !e.expired_at).length} 条关系`
  } catch (e: any) {
    status.value = '加载失败: ' + (e.message || e)
  }
}

function startPolling() {
  if (pollTimer.value) return
  let count = 0
  pollTimer.value = window.setInterval(async () => {
    count++
    status.value = `等待处理中... (${count * 5}s)`
    await refreshGraph()
    if (count >= 12) {
      // Stop after 60s
      stopPolling()
      status.value += ' (轮询结束)'
    }
  }, 5000)
}

function stopPolling() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

async function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  const file = target.files[0]

  loading.value = true
  status.value = `正在上传 ${file.name}...`
  try {
    const eps = await uploadFile(GROUP_ID, THREAD_ID, file)
    episodes.value = eps
    status.value = `上传成功: ${eps.length} 个文档片段已入库，等待 Celery 处理...`
    startPolling()
  } catch (e: any) {
    status.value = '上传失败: ' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
    target.value = ''
  }
}

async function handleTextSubmit() {
  if (!textInput.value.trim()) return
  loading.value = true
  status.value = '正在提交...'
  try {
    const ep = await ingestText(GROUP_ID, THREAD_ID, textInput.value.trim())
    episodes.value.push(ep)
    status.value = '提交成功，等待 Celery 处理...'
    textInput.value = ''
    startPolling()
  } catch (e: any) {
    status.value = '提交失败: ' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

// Initial load
refreshGraph()
</script>

<template>
  <div class="app">
    <header>
      <h1>Fuxi 知识图谱</h1>
      <p class="subtitle">上传文档或输入文本，自动提取实体关系并可视化</p>
    </header>

    <div class="controls">
      <div class="upload-section">
        <label class="upload-btn" :class="{ disabled: loading }">
          📄 上传文档
          <input type="file" accept=".pdf,.txt,.md,.json,.csv" @change="handleFileUpload" :disabled="loading" hidden />
        </label>
        <span class="hint">支持 PDF / TXT / MD / JSON / CSV</span>
      </div>

      <div class="text-section">
        <textarea
          v-model="textInput"
          placeholder="或直接输入文本内容..."
          rows="3"
          :disabled="loading"
        ></textarea>
        <button @click="handleTextSubmit" :disabled="loading || !textInput.trim()" class="submit-btn">
          提交
        </button>
      </div>

      <div class="actions">
        <button @click="refreshGraph" :disabled="loading" class="refresh-btn">刷新图谱</button>
        <span class="status" v-if="status">{{ status }}</span>
      </div>
    </div>

    <div class="graph-section">
      <GraphView :entities="entities" :edges="edges" />
    </div>

    <div class="legend">
      <span class="legend-item"><i style="background:#5B8FF9"></i> 人物</span>
      <span class="legend-item"><i style="background:#F6BD16"></i> 组织</span>
      <span class="legend-item"><i style="background:#5AD8A6"></i> 地点</span>
      <span class="legend-item"><i style="background:#945FB9"></i> 概念</span>
      <span class="legend-item"><i style="background:#FF6B3B"></i> 事件</span>
      <span class="legend-item"><i style="background:#269A99"></i> 产品</span>
    </div>
  </div>
</template>

<style scoped>
.app {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
header {
  margin-bottom: 24px;
}
h1 {
  font-size: 24px;
  margin: 0;
  color: #1a1a1a;
}
.subtitle {
  color: #666;
  font-size: 14px;
  margin: 4px 0 0;
}
.controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}
.upload-section {
  display: flex;
  align-items: center;
  gap: 12px;
}
.upload-btn {
  display: inline-block;
  padding: 8px 16px;
  background: #1677ff;
  color: #fff;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}
.upload-btn:hover { background: #4096ff; }
.upload-btn.disabled { background: #ccc; cursor: not-allowed; }
.hint { color: #999; font-size: 12px; }
.text-section {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
textarea {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  resize: vertical;
  font-family: inherit;
}
textarea:focus { outline: none; border-color: #1677ff; }
.submit-btn {
  padding: 8px 20px;
  background: #1677ff;
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  height: fit-content;
}
.submit-btn:hover { background: #4096ff; }
.submit-btn:disabled { background: #ccc; cursor: not-allowed; }
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.refresh-btn {
  padding: 6px 14px;
  background: #fff;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.refresh-btn:hover { border-color: #1677ff; color: #1677ff; }
.status { color: #666; font-size: 13px; }
.graph-section { margin-bottom: 16px; }
.legend {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #666;
}
.legend-item i {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
}
</style>
