<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { createProject } from '../api'

const router = useRouter()

const showModal = ref(false)
const projectName = ref('')
const projectDesc = ref('')
const isCreating = ref(false)
const createError = ref('')

function openModal() {
  projectName.value = ''
  projectDesc.value = ''
  createError.value = ''
  showModal.value = true
}

function scrollToFeatures() {
  const element = document.getElementById('features')
  element?.scrollIntoView({ behavior: 'smooth' })
}

function goToProjects() {
  router.push('/projects')
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

const features = [
  {
    icon: 'graph',
    title: '知识图谱构建',
    description: '自动从文档中提取实体关系，构建动态知识网络，支持多源数据融合与实时更新',
    color: '#155EEF'
  },
  {
    icon: 'timeline',
    title: '多世界线推演',
    description: '基于知识图谱推演多个可能的未来场景，量化评估每条世界线的发展路径与风险',
    color: '#8b5cf6'
  },
  {
    icon: 'agent',
    title: '智能体仿真',
    description: '为关键实体生成 AI 智能体，模拟真实决策行为，探索复杂系统的演化规律',
    color: '#F79009'
  },
  {
    icon: 'report',
    title: '智能报告生成',
    description: '自动生成推演报告，总结关键事件、风险点和机遇，辅助战略决策',
    color: '#12B76A'
  }
]

const useCases = [
  {
    title: '战略分析',
    description: '企业竞争格局、市场趋势预测、投资决策支持',
    icon: '🎯'
  },
  {
    title: '风险评估',
    description: '系统性风险识别、危机预警、应急方案推演',
    icon: '🛡️'
  },
  {
    title: '研究探索',
    description: '学术研究、政策影响评估、科技发展趋势',
    icon: '🔬'
  }
]
</script>

<template>
  <div class="landing-page">
    <!-- Navbar -->
    <nav class="navbar">
      <div class="navbar-inner">
        <div class="logo">
          <div class="logo-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L2 7l10 5 10-5-10-5z" fill="currentColor" opacity="0.6"/>
              <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="logo-text">
            <span class="logo-name">伏羲</span>
            <span class="logo-subtitle">Fuxi</span>
          </div>
        </div>

        <div class="nav-actions">
          <button class="btn-text" @click="scrollToFeatures">产品特性</button>
          <button class="btn-text" @click="goToProjects">我的项目</button>
          <button class="btn-primary" @click="openModal">
            开始使用
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M6 12l4-4-4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
    </nav>

    <!-- Hero Section -->
    <section class="hero">
      <div class="hero-content">
        <div class="hero-badge">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 2l1.5 4.5L14 8l-4.5 1.5L8 14l-1.5-4.5L2 8l4.5-1.5L8 2z" fill="currentColor"/>
          </svg>
          多世界线推演系统
        </div>

        <h1 class="hero-title">
          从<span class="gradient-text">知识图谱</span><br/>
          到<span class="gradient-text">未来推演</span>
        </h1>

        <p class="hero-desc">
          自动构建知识网络，模拟多个可能的未来场景<br/>
          量化评估风险与机遇，辅助战略决策
        </p>

        <div class="hero-actions">
          <button class="btn-hero-primary" @click="openModal">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M10 4v12M4 10h12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
            </svg>
            创建项目
          </button>
          <button class="btn-hero-secondary" @click="scrollToFeatures">
            了解更多
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M9 5v8M5 9l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>

        <!-- Stats -->
        <div class="hero-stats">
          <div class="stat">
            <div class="stat-icon">📊</div>
            <div class="stat-value">知识图谱</div>
            <div class="stat-label">自动提取实体关系</div>
          </div>
          <div class="stat">
            <div class="stat-icon">🌐</div>
            <div class="stat-value">世界线推演</div>
            <div class="stat-label">探索多种可能性</div>
          </div>
          <div class="stat">
            <div class="stat-icon">🤖</div>
            <div class="stat-value">智能体仿真</div>
            <div class="stat-label">模拟真实决策</div>
          </div>
        </div>
      </div>

      <!-- Hero Visual -->
      <div class="hero-visual">
        <div class="visual-card">
          <div class="visual-header">
            <div class="visual-dot"></div>
            <div class="visual-dot"></div>
            <div class="visual-dot"></div>
          </div>
          <div class="visual-content">
            <svg viewBox="0 0 400 300" class="graph-preview">
              <!-- 简化的图谱预览 -->
              <defs>
                <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" style="stop-color:#155EEF;stop-opacity:1" />
                  <stop offset="100%" style="stop-color:#8b5cf6;stop-opacity:1" />
                </linearGradient>
              </defs>

              <!-- Edges -->
              <path d="M200,150 Q250,100 300,150" stroke="#E0E0E0" stroke-width="2" fill="none"/>
              <path d="M200,150 Q250,200 300,150" stroke="#E0E0E0" stroke-width="2" fill="none"/>
              <path d="M100,150 Q150,100 200,150" stroke="#E0E0E0" stroke-width="2" fill="none"/>
              <path d="M100,150 Q150,200 200,150" stroke="#E0E0E0" stroke-width="2" fill="none"/>

              <!-- Nodes -->
              <circle cx="200" cy="150" r="20" fill="url(#grad1)"/>
              <circle cx="100" cy="150" r="16" fill="#155EEF"/>
              <circle cx="300" cy="150" r="16" fill="#8b5cf6"/>
              <circle cx="200" cy="80" r="14" fill="#F79009"/>
              <circle cx="200" cy="220" r="14" fill="#12B76A"/>
            </svg>
          </div>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section id="features" class="features">
      <div class="section-header">
        <h2 class="section-title">核心能力</h2>
        <p class="section-desc">基于 AI 的知识图谱与多世界线推演引擎</p>
      </div>

      <div class="features-grid">
        <div v-for="feature in features" :key="feature.title" class="feature-card">
          <div class="feature-icon" :style="{ background: feature.color + '15', color: feature.color }">
            <svg v-if="feature.icon === 'graph'" width="28" height="28" viewBox="0 0 28 28" fill="none">
              <path d="M14 5L5 10l9 5 9-5-9-5z" fill="currentColor" opacity="0.6"/>
              <path d="M5 18l9 5 9-5M5 14l9 5 9-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <svg v-else-if="feature.icon === 'timeline'" width="28" height="28" viewBox="0 0 28 28" fill="none">
              <circle cx="14" cy="8" r="3" stroke="currentColor" stroke-width="2"/>
              <circle cx="8" cy="18" r="3" stroke="currentColor" stroke-width="2"/>
              <circle cx="20" cy="18" r="3" stroke="currentColor" stroke-width="2"/>
              <path d="M12 10l-3 6M16 10l3 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <svg v-else-if="feature.icon === 'agent'" width="28" height="28" viewBox="0 0 28 28" fill="none">
              <circle cx="14" cy="10" r="4" stroke="currentColor" stroke-width="2"/>
              <path d="M8 24c0-3.3 2.7-6 6-6s6 2.7 6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              <path d="M19 13l3 3-3 3M9 13l-3 3 3 3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <svg v-else-if="feature.icon === 'report'" width="28" height="28" viewBox="0 0 28 28" fill="none">
              <rect x="6" y="4" width="16" height="20" rx="2" stroke="currentColor" stroke-width="2"/>
              <path d="M10 10h8M10 14h8M10 18h5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <h3 class="feature-title">{{ feature.title }}</h3>
          <p class="feature-desc">{{ feature.description }}</p>
        </div>
      </div>
    </section>

    <!-- Use Cases Section -->
    <section class="use-cases">
      <div class="section-header">
        <h2 class="section-title">应用场景</h2>
        <p class="section-desc">为不同领域提供决策支持</p>
      </div>

      <div class="use-cases-grid">
        <div v-for="useCase in useCases" :key="useCase.title" class="use-case-card">
          <div class="use-case-icon">{{ useCase.icon }}</div>
          <h3 class="use-case-title">{{ useCase.title }}</h3>
          <p class="use-case-desc">{{ useCase.description }}</p>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="cta">
      <div class="cta-content">
        <h2 class="cta-title">开始探索未来的可能性</h2>
        <p class="cta-desc">创建你的第一个项目，体验 AI 驱动的知识图谱与推演能力</p>
        <button class="btn-cta" @click="openModal">
          免费开始使用
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7 15l5-5-5-5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
      <div class="footer-content">
        <div class="footer-brand">
          <div class="logo">
            <div class="logo-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L2 7l10 5 10-5-10-5z" fill="currentColor" opacity="0.6"/>
                <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="logo-name">伏羲 Fuxi</span>
          </div>
          <p class="footer-tagline">多世界线推演系统</p>
        </div>

        <div class="footer-info">
          <p class="footer-text">© 2026 Fuxi. MVP Preview Version</p>
        </div>
      </div>
    </footer>

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
              <label class="field-label mt">项目描述</label>
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
.landing-page {
  min-height: 100vh;
  background: var(--bg-white);
  overflow-x: hidden;
}

/* ===== Navbar ===== */
.navbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border-secondary);
}

.navbar-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 var(--space-8);
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.logo-icon {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #155EEF 0%, #8b5cf6 100%);
  color: white;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(21, 94, 239, 0.15);
}

.logo-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.logo-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1;
  letter-spacing: -0.5px;
}

.logo-subtitle {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-quaternary);
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.btn-text {
  padding: 8px 16px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: color var(--transition-fast);
}

.btn-text:hover {
  color: var(--text-primary);
}

/* ===== Buttons ===== */
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
  box-shadow: 0 1px 2px rgba(21, 94, 239, 0.12);
}

.btn-primary:hover {
  background: var(--primary-hover);
  box-shadow: 0 4px 12px rgba(21, 94, 239, 0.24);
  transform: translateY(-1px);
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
  border-color: var(--gray-400);
}

/* ===== Hero Section ===== */
.hero {
  max-width: 1280px;
  margin: 0 auto;
  padding: 120px var(--space-8) 100px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 80px;
  align-items: center;
}

.hero-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #EFF4FF 0%, #F3E8FF 100%);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius-full);
  color: var(--primary);
  font-size: 13px;
  font-weight: 600;
  width: fit-content;
}

.hero-badge svg {
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.1); opacity: 0.8; }
}

.hero-title {
  font-size: 56px;
  font-weight: 800;
  line-height: 1.15;
  color: var(--text-primary);
  letter-spacing: -1.5px;
  margin: 0;
}

.gradient-text {
  background: linear-gradient(135deg, #155EEF 0%, #8b5cf6 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-desc {
  font-size: 18px;
  line-height: 1.7;
  color: var(--text-tertiary);
  margin: 0;
}

.hero-actions {
  display: flex;
  gap: var(--space-4);
  margin-top: var(--space-2);
}

.btn-hero-primary {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 16px 32px;
  background: linear-gradient(135deg, #155EEF 0%, #004ACD 100%);
  color: white;
  border: none;
  border-radius: var(--radius-lg);
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-normal);
  box-shadow: 0 4px 16px rgba(21, 94, 239, 0.3);
}

.btn-hero-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(21, 94, 239, 0.4);
}

.btn-hero-secondary {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 16px 32px;
  background: var(--bg-white);
  color: var(--text-secondary);
  border: 2px solid var(--border-primary);
  border-radius: var(--radius-lg);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-hero-secondary:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-light);
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-6);
  margin-top: var(--space-6);
  padding-top: var(--space-6);
  border-top: 1px solid var(--border-secondary);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stat-icon {
  font-size: 28px;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--text-quaternary);
}

/* Hero Visual */
.hero-visual {
  position: relative;
}

.visual-card {
  background: var(--bg-white);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-xl);
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.08);
  animation: float 6s ease-in-out infinite;
}

.visual-header {
  display: flex;
  gap: 8px;
  padding: 16px;
  background: var(--gray-50);
  border-bottom: 1px solid var(--border-secondary);
}

.visual-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--gray-300);
}

.visual-dot:nth-child(1) { background: #FF5F57; }
.visual-dot:nth-child(2) { background: #FFBD2E; }
.visual-dot:nth-child(3) { background: #28CA42; }

.visual-content {
  padding: 40px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
}

.graph-preview {
  width: 100%;
  height: auto;
}

.graph-preview circle {
  animation: nodeFloat 3s ease-in-out infinite;
}

.graph-preview circle:nth-child(2) { animation-delay: 0.2s; }
.graph-preview circle:nth-child(3) { animation-delay: 0.4s; }
.graph-preview circle:nth-child(4) { animation-delay: 0.6s; }
.graph-preview circle:nth-child(5) { animation-delay: 0.8s; }

@keyframes nodeFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}

/* ===== Features Section ===== */
.features {
  max-width: 1280px;
  margin: 0 auto;
  padding: 100px var(--space-8);
  background: var(--bg-page);
}

.section-header {
  text-align: center;
  margin-bottom: 64px;
}

.section-title {
  font-size: 42px;
  font-weight: 800;
  color: var(--text-primary);
  margin: 0 0 16px;
  letter-spacing: -1px;
}

.section-desc {
  font-size: 18px;
  color: var(--text-tertiary);
  margin: 0;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-6);
}

.feature-card {
  background: var(--bg-white);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  transition: all var(--transition-normal);
  cursor: pointer;
}

.feature-card:hover {
  border-color: var(--primary-border);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.08);
  transform: translateY(-4px);
}

.feature-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-4);
}

.feature-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 12px;
  letter-spacing: -0.3px;
}

.feature-desc {
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-tertiary);
  margin: 0;
}

/* ===== Use Cases Section ===== */
.use-cases {
  max-width: 1280px;
  margin: 0 auto;
  padding: 100px var(--space-8);
}

.use-cases-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-6);
}

.use-case-card {
  background: linear-gradient(135deg, var(--primary-light) 0%, var(--bg-white) 100%);
  border: 1px solid var(--border-secondary);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  text-align: center;
  transition: all var(--transition-normal);
}

.use-case-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(21, 94, 239, 0.12);
  border-color: var(--primary-border);
}

.use-case-icon {
  font-size: 48px;
  margin-bottom: var(--space-4);
}

.use-case-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.use-case-desc {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-tertiary);
  margin: 0;
}

/* ===== CTA Section ===== */
.cta {
  background: linear-gradient(135deg, #155EEF 0%, #8b5cf6 100%);
  padding: 100px var(--space-8);
  position: relative;
  overflow: hidden;
}

.cta::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -10%;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.1) 0%, transparent 70%);
  border-radius: 50%;
}

.cta-content {
  max-width: 800px;
  margin: 0 auto;
  text-align: center;
  position: relative;
  z-index: 1;
}

.cta-title {
  font-size: 42px;
  font-weight: 800;
  color: white;
  margin: 0 0 20px;
  letter-spacing: -1px;
}

.cta-desc {
  font-size: 18px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.9);
  margin: 0 0 40px;
}

.btn-cta {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 18px 40px;
  background: white;
  color: var(--primary);
  border: none;
  border-radius: var(--radius-lg);
  font-size: 17px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-normal);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.btn-cta:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2);
}

/* ===== Footer ===== */
.footer {
  background: var(--gray-900);
  padding: 60px var(--space-8) 40px;
}

.footer-content {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-brand {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.footer-brand .logo-icon {
  background: linear-gradient(135deg, #155EEF 0%, #8b5cf6 100%);
}

.footer-brand .logo-name {
  color: white;
}

.footer-tagline {
  font-size: 13px;
  color: var(--gray-400);
  margin: 0;
}

.footer-info {
  text-align: right;
}

.footer-text {
  font-size: 13px;
  color: var(--gray-500);
  margin: 0;
}

/* Responsive */
@media (max-width: 1024px) {
  .hero {
    grid-template-columns: 1fr;
    gap: 60px;
    padding: 80px var(--space-6);
  }

  .hero-title {
    font-size: 42px;
  }

  .features-grid {
    grid-template-columns: 1fr;
  }

  .use-cases-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .navbar-inner {
    padding: 0 var(--space-4);
  }

  .hero {
    padding: 60px var(--space-4);
  }

  .hero-title {
    font-size: 36px;
  }

  .hero-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-stats {
    grid-template-columns: 1fr;
  }

  .section-title {
    font-size: 32px;
  }

  .cta-title {
    font-size: 32px;
  }

  .footer-content {
    flex-direction: column;
    gap: var(--space-6);
    text-align: center;
  }

  .footer-info {
    text-align: center;
  }
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
  padding: var(--space-4);
}

.modal {
  background: var(--bg-white);
  border-radius: var(--radius-xl);
  width: 520px;
  max-width: 100%;
  box-shadow: 0 24px 48px rgba(16, 24, 40, 0.2);
  border: 1px solid var(--border-secondary);
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
  letter-spacing: -0.3px;
}

.modal-close {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-quaternary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
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
  gap: var(--space-4);
}

.field-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
  display: block;
}

.required {
  color: var(--danger);
  margin-left: 2px;
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
  background: var(--bg-input);
}

.field-input:hover:not(:focus) {
  border-color: var(--gray-400);
}

.field-input:focus {
  border-color: var(--primary);
  box-shadow: var(--shadow-focus);
  background: var(--bg-white);
}

.field-textarea {
  resize: vertical;
  min-height: 96px;
  line-height: 1.6;
}

.field-error {
  font-size: 13px;
  color: var(--danger);
  margin: 0;
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
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

/* Modal Transitions */
.modal-enter-active,
.modal-leave-active {
  transition: opacity var(--transition-normal);
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal {
  transition: transform var(--transition-normal) cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-leave-active .modal {
  transition: transform var(--transition-fast) ease-in;
}

.modal-enter-from .modal {
  transform: scale(0.95) translateY(20px);
}

.modal-leave-to .modal {
  transform: scale(0.98) translateY(-10px);
}
</style>
