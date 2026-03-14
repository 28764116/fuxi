<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listProjects, createProject, deleteProject } from '../api'
import type { Project } from '../api'

const router = useRouter()
const projects = ref<Project[]>([])
const isLoading = ref(true)

const showModal = ref(false)
const projectName = ref('')
const projectDesc = ref('')
const isCreating = ref(false)
const createError = ref('')

async function loadProjects() {
  try {
    projects.value = await listProjects()
  } catch (e) {
    console.error(e)
  } finally {
    isLoading.value = false
  }
}

async function handleDelete(e: Event, id: string) {
  e.stopPropagation()
  if (!confirm('确认删除该项目及其所有数据？')) return
  await deleteProject(id)
  projects.value = projects.value.filter(p => p.id !== id)
}

function formatDate(s: string) {
  try {
    const d = new Date(s)
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  } catch { return '' }
}

function projectInitial(name: string) {
  return name ? name[0].toUpperCase() : 'P'
}

const COLORS = ['#155EEF','#8b5cf6','#F79009','#12B76A','#ec4899','#3b82f6','#ef4444','#14b8a6']
function projectColor(id: string) {
  let n = 0
  for (const c of id) n += c.charCodeAt(0)
  return COLORS[n % COLORS.length]
}

function openModal() {
  projectName.value = ''
  projectDesc.value = ''
  createError.value = ''
  showModal.value = true
}

async function handleCreate() {
  if (!projectName.value.trim() || isCreating.value) return
  isCreating.value = true
  createError.value = ''
  try {
    const project = await createProject(projectName.value.trim(), projectDesc.value.trim() || undefined)
    showModal.value = false
    router.push(`/project/${project.id}`)
  } catch (e: any) {
    createError.value = e.response?.data?.detail || e.message || '创建失败'
    isCreating.value = false
  }
}

onMounted(loadProjects)
</script>

<template>
  <div class="projects-page">
    <div class="page-header">
      <div class="header-content">
        <div class="header-left">
          <button class="btn-back" @click="router.push('/')">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M12 5l-5 5 5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
          <div>
            <h1 class="page-title">我的项目</h1>
            <p class="page-desc">管理你的知识图谱项目</p>
          </div>
        </div>
        <button class="btn-primary" @click="openModal">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          新建项目
        </button>
      </div>
    </div>

    <div class="page-body">
      <!-- Loading -->
      <div v-if="isLoading" class="center-state">
        <div class="spinner"></div>
      </div>

      <!-- Empty -->
      <div v-else-if="projects.length === 0" class="empty">
        <div class="empty-icon">📊</div>
        <p class="empty-title">还没有项目</p>
        <p class="empty-desc">创建第一个项目，开始构建知识图谱</p>
        <button class="btn-primary btn-lg" @click="openModal">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M9 4v10M4 9h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          新建项目
        </button>
      </div>

      <!-- Grid -->
      <div v-else class="projects-grid">
        <div
          v-for="project in projects"
          :key="project.id"
          class="project-card"
          @click="router.push(`/project/${project.id}`)"
        >
          <div class="card-header">
            <div class="card-icon" :style="{ background: projectColor(project.id) }">
              {{ projectInitial(project.name) }}
            </div>
            <button class="card-delete" @click="handleDelete($event, project.id)">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 4h12M5.5 4V3a.5.5 0 01.5-.5h4a.5.5 0 01.5.5v1M7 7v5M9 7v5M3 4l.8 9a.5.5 0 00.5.5h7.4a.5.5 0 00.5-.5l.8-9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
          </div>
          <div class="card-body">
            <h3 class="card-title">{{ project.name }}</h3>
            <p class="card-desc">{{ project.description || '暂无描述' }}</p>
          </div>
          <div class="card-footer">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M7 12.5A5.5 5.5 0 107 1.5a5.5 5.5 0 000 11z" stroke="currentColor" stroke-width="1.2"/>
              <path d="M7 4v3l2 1" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
            {{ formatDate(project.created_at) }}
          </div>
        </div>
      </div>
    </div>

    <!-- Create Modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showModal" class="modal-mask" @click.self="showModal = false">
          <div class="modal">
            <div class="modal-header">
              <span class="modal-title">新建项目</span>
              <button class="modal-close" @click="showModal = false">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
              </button>
            </div>
            <div class="modal-body">
              <label class="field-label">项目名称 <span class="required">*</span></label>
              <input
                v-model="projectName"
                class="field-input"
                placeholder="例：科技公司竞争格局分析"
                autofocus
                @keydown.enter="handleCreate"
              />
              <label class="field-label">项目描述</label>
              <textarea
                v-model="projectDesc"
                class="field-input field-textarea"
                placeholder="可选：描述分析目标与背景"
                rows="3"
              ></textarea>
              <p v-if="createError" class="field-error">{{ createError }}</p>
            </div>
            <div class="modal-footer">
              <button class="btn-cancel" @click="showModal = false">取消</button>
              <button
                class="btn-primary"
                :disabled="!projectName.trim() || isCreating"
                @click="handleCreate"
              >{{ isCreating ? '创建中...' : '创建' }}</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.projects-page {
  min-height: 100vh;
  background: var(--bg-page);
}

.page-header {
  background: var(--bg-white);
  border-bottom: 1px solid var(--border-secondary);
  padding: var(--space-8);
}

.header-content {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.btn-back {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-hover);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-back:hover {
  background: var(--bg-white);
  border-color: var(--primary);
  color: var(--primary);
}

.page-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  margin: 0 0 8px;
  letter-spacing: -0.5px;
}

.page-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 10px 20px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary:hover {
  background: var(--primary-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(21, 94, 239, 0.24);
}

.btn-primary.btn-lg {
  padding: 12px 24px;
  font-size: 15px;
}

.page-body {
  max-width: 1280px;
  margin: 0 auto;
  padding: var(--space-8);
}

.center-state {
  display: flex;
  justify-content: center;
  padding: 120px 0;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--gray-200);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.empty {
  text-align: center;
  padding: 100px var(--space-6);
}

.empty-icon {
  font-size: 64px;
  margin-bottom: var(--space-4);
}

.empty-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.empty-desc {
  font-size: 15px;
  color: var(--text-tertiary);
  margin: 0 0 var(--space-6);
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-5);
}

.project-card {
  background: var(--bg-white);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.project-card:hover {
  border-color: var(--primary-border);
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);
}

.card-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 20px;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
}

.card-delete {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-quaternary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  opacity: 0;
  transition: all var(--transition-fast);
}

.project-card:hover .card-delete {
  opacity: 1;
}

.card-delete:hover {
  background: var(--danger-light);
  color: var(--danger);
}

.card-body {
  margin-bottom: var(--space-3);
}

.card-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
  letter-spacing: -0.2px;
}

.card-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-secondary);
  font-size: 12px;
  color: var(--text-quaternary);
}

/* Modal */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--bg-white);
  border-radius: var(--radius-xl);
  width: 520px;
  max-width: 90vw;
  box-shadow: 0 24px 48px rgba(16, 24, 40, 0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-6);
  padding-bottom: var(--space-4);
}

.modal-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.modal-close {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-quaternary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.modal-close:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.modal-body {
  padding: 0 var(--space-6) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.field-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.required {
  color: var(--danger);
}

.field-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  box-sizing: border-box;
  font-family: inherit;
  transition: all var(--transition-fast);
}

.field-input:focus {
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
}

.field-textarea {
  resize: vertical;
  min-height: 80px;
}

.field-error {
  font-size: 13px;
  color: var(--danger);
  margin: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  padding: var(--space-5) var(--space-6);
  border-top: 1px solid var(--border-secondary);
  background: var(--gray-25);
  border-radius: 0 0 var(--radius-xl) var(--radius-xl);
}

.btn-cancel {
  padding: 10px 20px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-cancel:hover {
  background: var(--bg-hover);
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity var(--transition-normal);
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal {
  transition: transform var(--transition-normal);
}

.modal-enter-from .modal {
  transform: scale(0.95) translateY(20px);
}
</style>
