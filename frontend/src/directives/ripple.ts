import type { Directive } from 'vue'

export const vRipple: Directive = {
  mounted(el: HTMLElement) {
    el.style.position = 'relative'
    el.style.overflow = 'hidden'

    el.addEventListener('click', function(e: MouseEvent) {
      const ripple = document.createElement('span')
      const rect = el.getBoundingClientRect()
      const size = Math.max(rect.width, rect.height)
      const x = e.clientX - rect.left - size / 2
      const y = e.clientY - rect.top - size / 2

      ripple.style.width = ripple.style.height = size + 'px'
      ripple.style.left = x + 'px'
      ripple.style.top = y + 'px'
      ripple.classList.add('ripple-effect')

      el.appendChild(ripple)

      setTimeout(() => ripple.remove(), 600)
    })
  },
}
