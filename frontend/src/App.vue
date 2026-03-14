<script setup lang="ts">
import { useRoute } from 'vue-router'
import { ref, computed } from 'vue'
import ToastContainer from './components/ToastContainer.vue'

const route = useRoute()
const sidebarCollapsed = ref(false)

const isHome = computed(() => route.name === 'home')

const navItems = [
  { path: '/', name: 'home', label: '首页', icon: 'home' },
]
</script>

<template>
  <div class="app-layout" :class="{ 'no-sidebar': isHome }">
    <!-- Sidebar -->
    <aside v-if="!isHome" class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <router-link to="/" class="logo">
          <span class="logo-icon">F</span>
          <span v-if="!sidebarCollapsed" class="logo-text">Fuxi</span>
        </router-link>
        <button v-if="!sidebarCollapsed" class="collapse-btn" @click="sidebarCollapsed = true">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M10 12L6 8l4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <button v-else class="collapse-btn" @click="sidebarCollapsed = false">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 12l4-4-4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>

      <nav class="sidebar-nav">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.name === item.name }"
        >
          <!-- Icons -->
          <svg v-if="item.icon === 'home'" class="nav-icon" width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M3 10l7-7 7 7M5 8.5V16a1 1 0 001 1h3v-4h2v4h3a1 1 0 001-1V8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <svg v-else-if="item.icon === 'graph'" class="nav-icon" width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="4" r="2.5" stroke="currentColor" stroke-width="1.5"/>
            <circle cx="4" cy="14" r="2.5" stroke="currentColor" stroke-width="1.5"/>
            <circle cx="16" cy="14" r="2.5" stroke="currentColor" stroke-width="1.5"/>
            <path d="M8.5 6l-3 6M11.5 6l3 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <svg v-else-if="item.icon === 'knowledge'" class="nav-icon" width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M10 2L2 6l8 4 8-4-8-4zM2 10l8 4 8-4M2 14l8 4 8-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <svg v-else-if="item.icon === 'live'" class="nav-icon" width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="3" fill="currentColor"/>
            <path d="M10 3v2M10 15v2M3 10h2M15 10h2M5.75 5.75l1.5 1.5M12.75 12.75l1.5 1.5M5.75 14.25l1.5-1.5M12.75 7.25l1.5-1.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <span v-if="!sidebarCollapsed" class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div v-if="route.name === 'project' && !sidebarCollapsed" class="project-badge">
          <span class="project-label">当前项目</span>
          <span class="project-id">{{ (route.params.id as string)?.slice(0, 8) }}...</span>
        </div>
        <div class="version-badge" :class="{ mini: sidebarCollapsed }">
          {{ sidebarCollapsed ? 'v0.1' : 'Fuxi v0.1-preview' }}
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="main-content" :class="{ 'with-sidebar': !isHome, 'sidebar-collapsed': !isHome && sidebarCollapsed }">
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- Toast Notifications -->
    <ToastContainer />
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
}

/* ===== Sidebar ===== */
.sidebar {
  width: var(--sidebar-width);
  height: 100vh;
  position: fixed;
  top: 0;
  left: 0;
  z-index: 50;
  display: flex;
  flex-direction: column;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-secondary);
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--shadow-sm);
}

.sidebar.collapsed {
  width: var(--sidebar-collapsed);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--header-height);
  padding: 0 var(--space-3);
  border-bottom: 1px solid var(--border-secondary);
  flex-shrink: 0;
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  text-decoration: none;
  color: var(--text-primary);
}

.logo-icon {
  width: 32px;
  height: 32px;
  background: var(--primary);
  color: white;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 16px;
  flex-shrink: 0;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.3px;
}

.collapse-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-quaternary);
}

.collapse-btn:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

/* Nav */
.sidebar-nav {
  flex: 1;
  padding: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  color: var(--text-tertiary);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: all var(--transition-fast);
}

.sidebar.collapsed .nav-item {
  justify-content: center;
  padding: var(--space-2);
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--bg-active);
  color: var(--primary);
}

.nav-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.nav-label {
  white-space: nowrap;
  overflow: hidden;
  opacity: 1;
  transition: opacity 0.2s ease;
}

.sidebar.collapsed .nav-label {
  opacity: 0;
}

/* Footer */
.sidebar-footer {
  padding: var(--space-3);
  border-top: 1px solid var(--border-secondary);
  flex-shrink: 0;
}

.project-badge {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: var(--space-2);
  padding: var(--space-2);
  background: var(--gray-50);
  border-radius: var(--radius-sm);
}

.project-label {
  font-size: 10px;
  color: var(--text-quaternary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.project-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-tertiary);
}

.version-badge {
  padding: var(--space-1) var(--space-2);
  background: var(--gray-50);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-quaternary);
  text-align: center;
}

/* ===== Main ===== */
.main-content {
  flex: 1;
  min-height: 100vh;
}

.main-content.with-sidebar {
  margin-left: var(--sidebar-width);
  transition: margin-left var(--transition-normal);
}

.main-content.sidebar-collapsed {
  margin-left: var(--sidebar-collapsed);
}

/* Page transition */
.page-fade-enter-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
