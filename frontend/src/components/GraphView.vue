<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Graph } from '@antv/g6'
import type { Entity, EntityEdge } from '../api'

const props = defineProps<{
  entities: Entity[]
  edges: EntityEdge[]
}>()

const containerRef = ref<HTMLDivElement>()
let graph: Graph | null = null

const TYPE_COLORS: Record<string, string> = {
  person: '#5B8FF9',
  organization: '#F6BD16',
  location: '#5AD8A6',
  concept: '#945FB9',
  event: '#FF6B3B',
  product: '#269A99',
  skill: '#FF9845',
  time: '#1E9493',
}

function getColor(type: string): string {
  return TYPE_COLORS[type] || '#aaa'
}

function buildGraphData() {
  const nodes = props.entities.map((e) => ({
    id: e.id,
    data: {
      label: e.name,
      entityType: e.entity_type,
    },
  }))

  const validNodeIds = new Set(props.entities.map((e) => e.id))
  const edgeList = props.edges
    .filter((e) => e.expired_at === null)
    .filter((e) => validNodeIds.has(e.source_entity_id) && validNodeIds.has(e.target_entity_id))
    .map((e) => ({
      id: e.id,
      source: e.source_entity_id,
      target: e.target_entity_id,
      data: {
        label: e.predicate,
        fact: e.fact,
      },
    }))

  return { nodes, edges: edgeList }
}

function renderGraph() {
  if (!containerRef.value) return
  const data = buildGraphData()
  if (data.nodes.length === 0) return

  if (graph) {
    graph.destroy()
    graph = null
  }

  const width = containerRef.value.clientWidth
  const height = containerRef.value.clientHeight || 500

  graph = new Graph({
    container: containerRef.value,
    width,
    height,
    data,
    layout: {
      type: 'd3-force',
      preventOverlap: true,
      nodeSize: 40,
      linkDistance: 180,
    },
    node: {
      style: {
        size: 36,
        fill: (d: any) => getColor(d.data?.entityType || ''),
        stroke: '#fff',
        lineWidth: 2,
        labelText: (d: any) => d.data?.label || '',
        labelFontSize: 13,
        labelFill: '#333',
        labelPlacement: 'bottom',
        labelOffsetY: 4,
      },
    },
    edge: {
      style: {
        stroke: '#C2C8D5',
        lineWidth: 1.5,
        endArrow: true,
        labelText: (d: any) => d.data?.label || '',
        labelFontSize: 10,
        labelFill: '#888',
        labelBackground: true,
        labelBackgroundFill: '#fff',
        labelBackgroundOpacity: 0.8,
        labelPadding: [2, 4],
      },
    },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
  })

  graph.render()
}

watch(
  () => [props.entities, props.edges],
  () => renderGraph(),
  { deep: true },
)

onMounted(() => {
  renderGraph()
})

onUnmounted(() => {
  if (graph) {
    graph.destroy()
    graph = null
  }
})
</script>

<template>
  <div ref="containerRef" class="graph-container"></div>
</template>

<style scoped>
.graph-container {
  width: 100%;
  height: 500px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: #fafafa;
}
</style>
