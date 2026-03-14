<script setup lang="ts">
import { useToast } from '../composables/useToast'

const { toasts, remove } = useToast()

const icons = {
  success: '✓',
  error: '✕',
  info: 'i',
  warning: '!',
}
</script>

<template>
  <div class="toast-container">
    <transition-group name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="toast"
        :class="toast.type"
        @click="remove(toast.id)"
      >
        <span class="toast-icon">{{ icons[toast.type] }}</span>
        <span class="toast-message">{{ toast.message }}</span>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: var(--space-6);
  right: var(--space-6);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-white);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  min-width: 320px;
  pointer-events: auto;
  cursor: pointer;
  border-left: 4px solid;
  animation: slideIn 0.3s ease;
}

.toast.success {
  border-left-color: var(--success);
}

.toast.error {
  border-left-color: var(--danger);
}

.toast.info {
  border-left-color: var(--primary);
}

.toast.warning {
  border-left-color: var(--warning);
}

.toast-icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.toast.success .toast-icon {
  background: var(--success-light);
  color: var(--success);
}

.toast.error .toast-icon {
  background: var(--danger-light);
  color: var(--danger);
}

.toast.info .toast-icon {
  background: var(--primary-light);
  color: var(--primary);
}

.toast.warning .toast-icon {
  background: var(--warning-light);
  color: var(--warning);
}

.toast-message {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.4;
}

/* Animations */
@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.toast-enter-active {
  animation: slideIn 0.3s ease;
}

.toast-leave-active {
  animation: slideIn 0.3s ease reverse;
}

.toast-move {
  transition: transform 0.3s ease;
}
</style>
