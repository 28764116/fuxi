<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import * as d3 from 'd3'

const { t, te } = useI18n()

// Entity and edge data from Neo4j
interface Entity {
  id: string  // UUID from Neo4j (backend returns as 'id' key)
  name: string
  entity_type: string
  summary?: string
  display_name?: string
  created_at?: string
}

interface EntityEdge {
  id: string  // UUID from Neo4j
  source_entity_id: string  // Source node UUID
  target_entity_id: string  // Target node UUID
  predicate: string  // Relationship type
  fact?: string
  valid_at?: string
  expired_at?: string | null
  episode_ids?: string[]
}

const props = defineProps<{
  entities: Entity[]
  edges: EntityEdge[]
  loading?: boolean
  mini?: boolean
  processing?: boolean  // 正在实时分析中
}>()

const containerRef = ref<HTMLDivElement>()
const graphSvg = ref<SVGSVGElement>()
const selectedItem = ref<{ type: 'node' | 'edge'; data: any; color?: string; entityType?: string } | null>(null)
const showEdgeLabels = ref(true)

let currentSimulation: any = null
let linkLabelsRef: any = null
let linkLabelBgRef: any = null

// 颜色调色板
const COLOR_PALETTE = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#3498db', '#9b59b6', '#27ae60', '#f39c12']

// 翻译实体类型名称
const translateEntityType = (type: string): string => {
  const key = `entityTypes.${type}`
  // 使用 te() 检查翻译键是否存在，避免警告
  if (te(key)) {
    return t(key)
  }
  // 翻译不存在：返回原始类型名，转换为易读格式
  // 例如: financial_instrument → Financial Instrument
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

// 动态计算所有实体类型（按数量降序排序，不合并）
const entityTypes = computed(() => {
  if (!props.entities || props.entities.length === 0) return []

  const typeMap: Record<string, { name: string; displayName: string; count: number; color: string }> = {}

  props.entities.forEach(entity => {
    const type = entity.entity_type || 'Unknown'
    if (!typeMap[type]) {
      const colorIndex = Object.keys(typeMap).length % COLOR_PALETTE.length
      typeMap[type] = {
        name: type,
        displayName: translateEntityType(type),
        count: 0,
        color: COLOR_PALETTE[colorIndex]
      }
    }
    typeMap[type].count++
  })

  // 按数量降序排序，全部显示（不合并为"其他"）
  return Object.values(typeMap).sort((a, b) => b.count - a.count)
})



function renderGraph() {
  if (!graphSvg.value || !containerRef.value) return
  if (props.entities.length === 0) return

  // Stop previous simulation
  if (currentSimulation) {
    currentSimulation.stop()
  }

  const container = containerRef.value
  const width = container.clientWidth
  const height = container.clientHeight

  const svg = d3.select(graphSvg.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)

  svg.selectAll('*').remove()

  // Build nodes and edges
  const nodeMap: Record<string, any> = {}
  const nodes = props.entities.map((e: Entity) => {
    // 优先使用 display_name（原始名称），如果没有则用 name（规范化名称）
    const displayName = e.display_name || e.name
    const node = {
      id: e.id,
      name: displayName,
      type: e.entity_type,
      rawData: e
    }
    nodeMap[e.id] = node
    return node
  })

  const nodeIds = new Set(nodes.map(n => n.id))

  // 🔥 Deduplicate edges by (source, target, predicate) triplet
  const edgeMap = new Map<string, EntityEdge>()
  let duplicateCount = 0
  props.edges.forEach((e: EntityEdge) => {
    const sourceId = e.source_entity_id
    const targetId = e.target_entity_id
    const predicate = e.predicate || 'RELATED'

    // Only keep edges with valid nodes
    if (!nodeIds.has(sourceId) || !nodeIds.has(targetId)) return

    // Deduplicate by (source, target, predicate)
    const key = `${sourceId}_${targetId}_${predicate}`
    if (edgeMap.has(key)) {
      duplicateCount++
      const existing = edgeMap.get(key)!
      console.log('⚠️ Duplicate edge in render:', {
        source: nodeMap[sourceId]?.name,
        target: nodeMap[targetId]?.name,
        predicate,
        existing_id: existing.id,
        duplicate_id: e.id
      })
    } else {
      edgeMap.set(key, e)
    }
  })
  const tempEdges = Array.from(edgeMap.values())

  if (duplicateCount > 0) {
    console.log(`🔍 GraphView: removed ${duplicateCount} duplicate edges in render`)
  }

  // Compute edge pair counts for curved edges
  const edgePairCount: Record<string, number> = {}

  tempEdges.forEach((e: EntityEdge) => {
    const pairKey = [e.source_entity_id, e.target_entity_id].sort().join('_')
    edgePairCount[pairKey] = (edgePairCount[pairKey] || 0) + 1
  })

  // Build edges with curvature
  const edgePairIndex: Record<string, number> = {}
  const edges = tempEdges.map((e: EntityEdge) => {
    const sourceId = e.source_entity_id
    const targetId = e.target_entity_id
    const pairKey = [sourceId, targetId].sort().join('_')
    const totalCount = edgePairCount[pairKey]
    const currentIndex = edgePairIndex[pairKey] || 0
    edgePairIndex[pairKey] = currentIndex + 1

    const isReversed = sourceId > targetId
    let curvature = 0
    if (totalCount > 1) {
      const curvatureRange = Math.min(1.2, 0.6 + totalCount * 0.15)
      curvature = ((currentIndex / (totalCount - 1)) - 0.5) * curvatureRange * 2
      if (isReversed) {
        curvature = -curvature
      }
    }

    return {
      source: sourceId,
      target: targetId,
      name: e.predicate || 'RELATED',
      curvature,
      pairIndex: currentIndex,
      pairTotal: totalCount,
      rawData: {
        ...e,
        source_name: nodeMap[sourceId]?.name,
        target_name: nodeMap[targetId]?.name
      }
    }
  })

  // Color map
  const colorMap: Record<string, string> = {}
  entityTypes.value.forEach(t => {
    colorMap[t.name] = t.color
  })

  // Simulation
  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id((d: any) => d.id).distance((d: any) => {
      const baseDistance = 150
      const edgeCount = d.pairTotal || 1
      return baseDistance + (edgeCount - 1) * 50
    }))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(50))
    .force('x', d3.forceX(width / 2).strength(0.04))
    .force('y', d3.forceY(height / 2).strength(0.04))

  currentSimulation = simulation

  const g = svg.append('g')

  // Zoom
  svg.call(d3.zoom().extent([[0, 0], [width, height]]).scaleExtent([0.1, 4]).on('zoom', (event) => {
    g.attr('transform', event.transform)
  }) as any)

  // Link path generator
  const getLinkPath = (d: any) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y

    if (d.curvature === 0) {
      return `M${sx},${sy} L${tx},${ty}`
    }

    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy)
    const pairTotal = d.pairTotal || 1
    const offsetRatio = 0.25 + pairTotal * 0.05
    const baseOffset = Math.max(35, dist * offsetRatio)
    const offsetX = -dy / dist * d.curvature * baseOffset
    const offsetY = dx / dist * d.curvature * baseOffset
    const cx = (sx + tx) / 2 + offsetX
    const cy = (sy + ty) / 2 + offsetY

    return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`
  }

  // 计算边中点（用于标签定位）
  const getLinkMidpoint = (d: any) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y

    if (d.curvature === 0) {
      return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
    }

    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy)
    const pairTotal = d.pairTotal || 1
    const offsetRatio = 0.25 + pairTotal * 0.05
    const baseOffset = Math.max(35, dist * offsetRatio)
    const offsetX = -dy / dist * d.curvature * baseOffset
    const offsetY = dx / dist * d.curvature * baseOffset
    const cx = (sx + tx) / 2 + offsetX
    const cy = (sy + ty) / 2 + offsetY
    // 二次贝塞尔曲线 t=0.5 中点
    return {
      x: 0.25 * sx + 0.5 * cx + 0.25 * tx,
      y: 0.25 * sy + 0.5 * cy + 0.25 * ty
    }
  }

  const handleEdgeClick = (event: any, d: any) => {
    event.stopPropagation()
    link.attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
    linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
    linkLabels.attr('fill', '#666')
    link.filter((l: any) => l === d).attr('stroke', '#3498db').attr('stroke-width', 3)
    selectedItem.value = { type: 'edge', data: d.rawData }
  }

  // Draw edges
  const linkGroup = g.append('g').attr('class', 'links')

  const link = linkGroup.selectAll('path')
    .data(edges)
    .enter().append('path')
    .attr('stroke', '#C0C0C0')
    .attr('stroke-width', 1.5)
    .attr('fill', 'none')
    .style('cursor', 'pointer')
    .on('click', handleEdgeClick)

  // Edge label backgrounds
  const linkLabelBg = linkGroup.selectAll('rect')
    .data(edges)
    .enter().append('rect')
    .attr('fill', 'rgba(255,255,255,0.95)')
    .attr('rx', 3)
    .attr('ry', 3)
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', handleEdgeClick)

  // Edge labels (improved readability)
  const linkLabels = linkGroup.selectAll('text')
    .data(edges)
    .enter().append('text')
    .text((d: any) => {
      const label = d.name
      // Truncate long labels
      return label.length > 12 ? label.substring(0, 12) + '…' : label
    })
    .attr('font-size', '10px')  // Increased from 9px
    .attr('fill', '#444')  // Darker for better contrast
    .attr('font-weight', '500')  // Medium weight
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'middle')
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('font-family', 'system-ui, -apple-system, sans-serif')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', handleEdgeClick)

  linkLabelsRef = linkLabels
  linkLabelBgRef = linkLabelBg

  // Draw nodes
  const nodeGroup = g.append('g').attr('class', 'nodes')

  const node = nodeGroup.selectAll('circle')
    .data(nodes)
    .enter().append('circle')
    .attr('r', 10)
    .attr('fill', (d: any) => colorMap[d.type] || '#999')
    .attr('stroke', '#fff')
    .attr('stroke-width', 2.5)
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event: any, d: any) => {
        d.fx = d.x
        d.fy = d.y
        d._dragStartX = event.x
        d._dragStartY = event.y
        d._isDragging = false
      })
      .on('drag', (event: any, d: any) => {
        const dx = event.x - d._dragStartX
        const dy = event.y - d._dragStartY
        const distance = Math.sqrt(dx * dx + dy * dy)

        if (!d._isDragging && distance > 3) {
          d._isDragging = true
          simulation.alphaTarget(0.3).restart()
        }

        if (d._isDragging) {
          d.fx = event.x
          d.fy = event.y
        }
      })
      .on('end', (event: any, d: any) => {
        if (d._isDragging) {
          simulation.alphaTarget(0)
        }
        d.fx = null
        d.fy = null
        d._isDragging = false
      })
    )
    .on('click', (event: any, d: any) => {
      event.stopPropagation()
      node.attr('stroke', '#fff').attr('stroke-width', 2.5)
      link.attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
      d3.select(event.target).attr('stroke', '#E91E63').attr('stroke-width', 4)
      link.filter((l: any) => l.source.id === d.id || l.target.id === d.id)
        .attr('stroke', '#E91E63')
        .attr('stroke-width', 2.5)

      selectedItem.value = {
        type: 'node',
        data: d.rawData,
        entityType: d.type,
        color: colorMap[d.type] || '#999'
      }
    })
    .on('mouseenter', (event: any, d: any) => {
      if (!selectedItem.value || (selectedItem.value.data as any)?.id !== d.rawData.id) {
        d3.select(event.target).attr('stroke', '#333').attr('stroke-width', 3)
      }
    })
    .on('mouseleave', (event: any, d: any) => {
      if (!selectedItem.value || (selectedItem.value.data as any)?.id !== d.rawData.id) {
        d3.select(event.target).attr('stroke', '#fff').attr('stroke-width', 2.5)
      }
    })

  // Node labels
  const nodeLabels = nodeGroup.selectAll('text')
    .data(nodes)
    .enter().append('text')
    .text((d: any) => d.name.length > 8 ? d.name.substring(0, 8) + '…' : d.name)
    .attr('font-size', '11px')
    .attr('fill', '#333')
    .attr('font-weight', '500')
    .attr('dx', 14)
    .attr('dy', 4)
    .style('pointer-events', 'none')
    .style('font-family', 'system-ui, sans-serif')

  // Simulation tick
  simulation.on('tick', () => {
    link.attr('d', (d: any) => getLinkPath(d))

    linkLabels.each(function(this: SVGTextElement, d: any) {
      const mid = getLinkMidpoint(d)
      d3.select(this).attr('x', mid.x).attr('y', mid.y)
    })

    linkLabelBg.each(function(this: SVGRectElement, d: any, i: number) {
      const mid = getLinkMidpoint(d)
      const textEl = (linkLabels.nodes() as SVGTextElement[])[i]
      try {
        const bbox = textEl.getBBox()
        d3.select(this)
          .attr('x', mid.x - bbox.width / 2 - 4)
          .attr('y', mid.y - bbox.height / 2 - 2)
          .attr('width', bbox.width + 8)
          .attr('height', bbox.height + 4)
      } catch { /* ignore during initial render */ }
    })

    node
      .attr('cx', (d: any) => d.x)
      .attr('cy', (d: any) => d.y)

    nodeLabels
      .attr('x', (d: any) => d.x)
      .attr('y', (d: any) => d.y)
  })

  // Click background to close detail panel
  svg.on('click', () => {
    selectedItem.value = null
    node.attr('stroke', '#fff').attr('stroke-width', 2.5)
    link.attr('stroke', '#C0C0C0').attr('stroke-width', 1.5)
    linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
    linkLabels.attr('fill', '#666')
  })
}

function closeDetailPanel() {
  selectedItem.value = null
}

// 使用防抖优化，避免频繁重构
let renderTimer: ReturnType<typeof setTimeout> | null = null

const debouncedRender = () => {
  if (renderTimer) clearTimeout(renderTimer)
  renderTimer = setTimeout(() => {
    nextTick(renderGraph)
  }, 300) // 300ms 防抖
}

// 监听数组长度变化和内容变化（浅层对比）
const entitiesKey = computed(() =>
  props.entities.map(e => (e as any).uuid || (e as any).id).sort().join(',')
)
const edgesKey = computed(() =>
  props.edges.map(e => (e as any).uuid || (e as any).id).sort().join(',')
)

watch([entitiesKey, edgesKey], () => {
  debouncedRender()
})

watch(showEdgeLabels, (val) => {
  if (linkLabelsRef) linkLabelsRef.style('display', val ? 'block' : 'none')
  if (linkLabelBgRef) linkLabelBgRef.style('display', val ? 'block' : 'none')
})

// Resize 防抖
let resizeTimer: ReturnType<typeof setTimeout> | null = null

function handleResize() {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    nextTick(renderGraph)
  }, 150) // 150ms 防抖
}

onMounted(() => {
  renderGraph()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (renderTimer) clearTimeout(renderTimer)
  if (resizeTimer) clearTimeout(resizeTimer)
  if (currentSimulation) {
    currentSimulation.stop()
  }
})
</script>

<template>
  <div class="graph-wrapper" :class="{ 'graph-wrapper--mini': mini }">
    <!-- 图谱容器 -->
    <div class="graph-container" ref="containerRef">
      <svg v-if="entities.length" ref="graphSvg" class="graph-svg"></svg>

      <!-- 加载状态 -->
      <div v-if="loading && !entities.length" class="graph-state">
        <div class="loading-spinner"></div>
        <p>{{ $t('common.processing') }}...</p>
      </div>

      <!-- 实时分析等待状态 -->
      <div v-else-if="processing && !entities.length" class="graph-state processing-state">
        <div class="processing-animation">
          <div class="wave"></div>
          <div class="wave"></div>
          <div class="wave"></div>
        </div>
        <p class="processing-text">{{ $t('graph.processingState') }}</p>
        <p class="processing-hint">{{ $t('graph.processingHint') }}</p>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!entities.length" class="graph-state">
        <div class="empty-icon">❖</div>
        <p class="empty-text">{{ $t('graph.emptyState') }}</p>
        <p class="empty-hint">{{ $t('graph.emptyHint') }}</p>
      </div>
    </div>

    <!-- 节点/边详情面板 -->
    <div v-if="selectedItem" class="detail-panel">
      <div class="detail-panel-header">
        <span class="detail-title">{{ selectedItem.type === 'node' ? '节点详情' : '关系详情' }}</span>
        <button class="detail-close" @click="closeDetailPanel">×</button>
      </div>

      <!-- 节点详情 -->
      <div v-if="selectedItem.type === 'node'" class="detail-content">
        <div class="detail-row">
          <span class="detail-label">名称:</span>
          <span class="detail-value">{{ selectedItem.data.display_name || selectedItem.data.name }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">类型:</span>
          <span class="detail-value">{{ selectedItem.data.entity_type }}</span>
        </div>
        <div v-if="selectedItem.data.summary" class="detail-row">
          <span class="detail-label">摘要:</span>
          <span class="summary-text">{{ selectedItem.data.summary }}</span>
        </div>
        <div v-if="selectedItem.data.created_at" class="detail-row">
          <span class="detail-label">创建:</span>
          <span class="detail-value">{{ new Date(selectedItem.data.created_at).toLocaleString('zh-CN') }}</span>
        </div>
      </div>

      <!-- 边详情 -->
      <div v-else class="detail-content">
        <div class="detail-row">
          <span class="detail-label">来源:</span>
          <span class="detail-value">{{ selectedItem.data.source_name }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">目标:</span>
          <span class="detail-value">{{ selectedItem.data.target_name }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">关系:</span>
          <span class="detail-value">{{ selectedItem.data.predicate }}</span>
        </div>
        <div v-if="selectedItem.data.fact" class="detail-row">
          <span class="detail-label">事实:</span>
          <span class="fact-text">{{ selectedItem.data.fact }}</span>
        </div>
        <div v-if="selectedItem.data.valid_at" class="detail-row">
          <span class="detail-label">生效时间:</span>
          <span class="detail-value">{{ new Date(selectedItem.data.valid_at).toLocaleString('zh-CN') }}</span>
        </div>
      </div>
    </div>

    <!-- 边标签开关 - 右上角 -->
    <div v-if="entities.length" class="edge-labels-toggle">
      <label class="toggle-switch">
        <input type="checkbox" v-model="showEdgeLabels" />
        <span class="slider"></span>
      </label>
      <span class="toggle-label">边标签</span>
    </div>

    <!-- 图例 - 左下角 -->
    <div v-if="entityTypes.length" class="graph-legend">
      <span class="legend-title">{{ $t('graph.entityTypes') }}</span>
      <div class="legend-items">
        <div class="legend-item" v-for="type in entityTypes" :key="type.name">
          <span class="legend-dot" :style="{ background: type.color }"></span>
          <span class="legend-label">{{ type.displayName }} ({{ type.count }})</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.graph-wrapper {
  position: relative;
  width: 100%;
  height: 500px;
}

.graph-wrapper--mini {
  height: 200px;
}

.graph-container {
  width: 100%;
  height: 100%;
  background-color: #FAFAFA;
  background-image: radial-gradient(#D0D0D0 1.5px, transparent 1.5px);
  background-size: 24px 24px;
  position: relative;
}

.graph-state {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e5e7eb;
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 48px;
  color: #cbd5e1;
  margin-bottom: 16px;
}

.empty-text {
  font-size: 16px;
  font-weight: 500;
  color: #475569;
  margin: 0 0 8px;
}

.empty-hint {
  font-size: 14px;
  color: #94a3b8;
  margin: 0;
}

/* 实时分析等待状态 */
.processing-state {
  background: linear-gradient(135deg, #faf5ff 0%, #f3f4f6 100%);
}

.processing-animation {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.wave {
  width: 12px;
  height: 40px;
  background: linear-gradient(135deg, var(--primary), #8b5cf6);
  border-radius: 6px;
  animation: wave 1.2s ease-in-out infinite;
}

.wave:nth-child(2) {
  animation-delay: 0.2s;
}

.wave:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes wave {
  0%, 100% {
    transform: scaleY(0.5);
    opacity: 0.6;
  }
  50% {
    transform: scaleY(1);
    opacity: 1;
  }
}

.processing-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--primary);
  margin: 0 0 8px;
}

.processing-hint {
  font-size: 14px;
  color: #8b5cf6;
  margin: 0;
  opacity: 0.8;
}

/* 详情面板 */
.detail-panel {
  position: absolute;
  top: 60px;
  right: 20px;
  width: 320px;
  max-height: calc(100% - 100px);
  background: white;
  border: 1px solid #EAEAEA;
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.1);
  z-index: 20;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.detail-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 16px;
  background: #FAFAFA;
  border-bottom: 1px solid #EEE;
  flex-shrink: 0;
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  flex: 1;
  color: #333;
}

.detail-type-badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  margin-left: auto;
  margin-right: 12px;
  color: #fff;
}

.detail-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
  line-height: 1;
  padding: 0;
  transition: color 0.2s;
}

.detail-close:hover {
  color: #333;
}

.detail-content {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
}

.detail-content::-webkit-scrollbar {
  width: 6px;
}

.detail-content::-webkit-scrollbar-thumb {
  background: #D0D0D0;
  border-radius: 3px;
}

.detail-row {
  margin-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 13px;
}

.detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  color: #888;
  font-size: 12px;
  font-weight: 500;
  min-width: 80px;
}

.detail-value {
  color: #333;
  flex: 1;
  word-break: break-word;
}

.uuid-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #666;
}

.summary-text,
.fact-text {
  line-height: 1.6;
  color: #444;
  font-size: 12px;
}

/* 图例 - 左下角 */
.graph-legend {
  position: absolute;
  bottom: 24px;
  left: 24px;
  background: rgba(255,255,255,0.95);
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #EAEAEA;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
  z-index: 10;
}

.legend-title {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #E91E63;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  max-width: 320px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #555;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  white-space: nowrap;
}

/* 边标签开关 */
.edge-labels-toggle {
  position: absolute;
  top: 16px;
  right: 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255,255,255,0.95);
  padding: 6px 12px;
  border-radius: 20px;
  border: 1px solid #E0E0E0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  z-index: 10;
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background: #E0E0E0;
  border-radius: 20px;
  transition: 0.25s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: 0.25s;
}

input:checked + .slider {
  background: #7B2D8E;
}

input:checked + .slider:before {
  transform: translateX(16px);
}

.toggle-label {
  font-size: 12px;
  color: #666;
  white-space: nowrap;
}
</style>
