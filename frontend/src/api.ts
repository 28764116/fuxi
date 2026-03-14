import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// 自动添加语言偏好到请求头
api.interceptors.request.use((config) => {
  const locale = localStorage.getItem('locale') || 'zh'
  config.headers['X-User-Language'] = locale
  return config
})

// ---- Memory types ----

export interface Entity {
  id: string
  group_id: string
  name: string
  display_name?: string | null  // 原始名称，优先显示这个
  entity_type: string
  summary: string | null
  created_at: string
  updated_at: string
}

export interface EntityEdge {
  id: string
  group_id: string
  source_entity_id: string
  target_entity_id: string
  predicate: string
  fact: string
  valid_at: string
  expired_at: string | null
  episode_ids: string[]
  created_at: string
}

export interface Episode {
  id: string
  group_id: string
  thread_id: string
  role: string
  content: string
  source_type: string
  valid_at: string
  created_at: string
}

// ---- Simulation types ----

export interface SimTask {
  id: string
  group_id: string
  title: string
  seed_content: string
  seed_type: string
  goal: string | null
  scene_type: string | null
  num_timelines: number
  num_agents: number
  num_rounds: number
  scenario: string
  status: string
  progress: number
  status_message: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface SimWorldline {
  id: string
  task_id: string
  graph_namespace: string
  initial_assumption: string | null
  assumption_type: string
  status: string
  score: number | null
  score_detail: Record<string, any> | null
  verdict: string | null
  created_at: string
  updated_at: string
}

export interface SimWorldlineEvent {
  id: string
  worldline_id: string
  agent_id: string | null
  sim_time: string | null
  step_index: number
  action_type: string | null
  description: string | null
  impact_score: number
  new_facts: any[] | null
  created_at: string
}

export interface SimAgent {
  id: string
  task_id: string
  entity_id: string | null
  name: string
  role: string | null
  background: string | null
  personality: string | null
  ideology: string | null
  influence_weight: number
  risk_tolerance: number
  change_resistance: number
  scene_metadata: Record<string, any> | null
  created_at: string
}

export interface SimReport {
  id: string
  task_id: string
  worldline_id: string | null
  title: string
  content: string
  report_type: string
  created_at: string
}

export interface SceneInfo {
  scene_type: string
  display_name: string
}

export interface GraphData {
  nodes: { id: string; name: string; entity_type: string; display_name: string | null; group_id: string }[]
  edges: { id: string; source_id: string; target_id: string; predicate: string; fact: string; generated_by: string | null; confidence: number | null; valid_at: string; expired_at: string | null }[]
  total_nodes: number
  total_edges: number
}

// ---- Memory API ----

export interface DocumentUploadResponse {
  task_id: string
  message: string
  file_name: string
  file_size: number
}

export interface DocumentTaskStatus {
  task_id: string
  state: string  // PENDING, PROGRESS, SUCCESS, FAILURE
  stage?: string
  progress: number
  current: number
  total: number
  result?: any
  error?: string
}

export async function uploadFile(groupId: string, threadId: string, file: File): Promise<DocumentUploadResponse> {
  const form = new FormData()
  form.append('group_id', groupId)
  form.append('thread_id', threadId)
  form.append('file', file)
  const { data } = await api.post('/memory/upload', form)
  return data
}

// WebSocket for upload progress
export function connectUploadWs(taskId: string, onMessage: (data: any) => void, onClose?: () => void): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${proto}//${window.location.host}/api/memory/ws/upload/${taskId}`)
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      onMessage(msg)
    } catch { /* ignore */ }
  }
  ws.onclose = () => onClose?.()
  ws.onerror = () => onClose?.()
  return ws
}

export async function getEntities(groupId: string): Promise<Entity[]> {
  const { data } = await api.get('/memory/entities', { params: { group_id: groupId, limit: 200 } })
  return data
}

export async function getEntityEdges(entityId: string): Promise<EntityEdge[]> {
  const { data } = await api.get(`/memory/entities/${entityId}/edges`)
  return data
}

export async function getAllEdges(groupId: string): Promise<EntityEdge[]> {
  const { data } = await api.get(`/memory/edges`, {
    params: { group_id: groupId, active_only: true, limit: 2000 }
  })
  return data
}

export async function ingestText(groupId: string, threadId: string, content: string): Promise<Episode> {
  const { data } = await api.post('/memory/episodes', {
    group_id: groupId,
    thread_id: threadId,
    role: 'user',
    content,
    valid_at: new Date().toISOString(),
  })
  return data
}

// ---- Projects API ----

export interface Project {
  id: string
  name: string
  description: string | null
  group_id: string
  created_at: string
  updated_at: string
}

export async function listProjects(): Promise<Project[]> {
  const { data } = await api.get('/memory/projects')
  return data
}

export async function createProject(name: string, description?: string): Promise<Project> {
  const { data } = await api.post('/memory/projects', { name, description })
  return data
}

export async function deleteProject(projectId: string): Promise<void> {
  await api.delete(`/memory/projects/${projectId}`)
}

// ---- Simulation API ----

export async function getScenes(): Promise<SceneInfo[]> {
  const { data } = await api.get('/simulation/scenes')
  return data
}

export async function createSimTask(payload: {
  group_id: string
  title: string
  seed_content: string
  seed_type?: string
  goal?: string
  scene_type?: string
  num_timelines?: number
  num_agents?: number
  num_rounds?: number
}): Promise<SimTask> {
  const { data } = await api.post('/simulation/tasks', payload)
  return data
}

export async function getSimTask(taskId: string): Promise<SimTask> {
  const { data } = await api.get(`/simulation/tasks/${taskId}`)
  return data
}

export async function getSimTaskStatus(taskId: string): Promise<SimTask> {
  const { data } = await api.get(`/simulation/tasks/${taskId}/status`)
  return data
}

export async function listSimTasks(groupId: string): Promise<SimTask[]> {
  const { data } = await api.get('/simulation/tasks', { params: { group_id: groupId } })
  return data
}

export async function getTaskWorldlines(taskId: string): Promise<SimWorldline[]> {
  const { data } = await api.get(`/simulation/tasks/${taskId}/worldlines`)
  return data
}

export async function getTaskAgents(taskId: string): Promise<SimAgent[]> {
  const { data } = await api.get(`/simulation/tasks/${taskId}/agents`)
  return data
}

export async function getTaskReports(taskId: string): Promise<SimReport[]> {
  const { data } = await api.get(`/simulation/tasks/${taskId}/reports`)
  return data
}

export async function getWorldlineEvents(worldlineId: string, limit = 200): Promise<SimWorldlineEvent[]> {
  const { data } = await api.get(`/simulation/worldlines/${worldlineId}/events`, { params: { limit } })
  return data
}

export async function getWorldlineSnapshot(worldlineId: string, t?: string): Promise<GraphData> {
  const params: any = {}
  if (t) params.t = t
  const { data } = await api.get(`/simulation/worldlines/${worldlineId}/snapshot`, { params })
  return data
}

export async function getGraph(groupId: string): Promise<GraphData> {
  const { data } = await api.get('/simulation/graph', { params: { group_id: groupId } })
  return data
}

// ---- Graph (Neo4j) API ----

export interface GraphNode {
  uuid: string
  name: string
  entity_type: string
  labels: string[]
  summary: string
  attributes: Record<string, any>
  created_at: string | null
}

export interface GraphEdge {
  uuid: string
  name: string
  source_node_uuid: string
  source_name: string
  target_node_uuid: string
  target_name: string
  fact: string
  created_at: string | null
}

export interface GraphProject {
  project_id: string
  name: string
  simulation_requirement: string
  ontology: {
    entity_types: string[]
    edge_types: string[]
  }
  status: string
  graph_id: string | null
  created_at: string
}

export interface GraphTask {
  task_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  message: string
  progress: number
  result: {
    graph_id: string
    node_count: number
    edge_count: number
  } | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface GraphDataResponse {
  graph_id: string
  node_count: number
  edge_count: number
  entity_types: string[]
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export async function generateOntology(formData: FormData): Promise<{ success: boolean; data: any; error?: string }> {
  const { data } = await api.post('/graph/ontology/generate', formData)
  return data
}

export async function buildGraph(projectId: string, graphName?: string): Promise<{ success: boolean; data: any; error?: string }> {
  const { data } = await api.post('/graph/build', {
    project_id: projectId,
    graph_name: graphName
  })
  return data
}

export async function getGraphTask(taskId: string): Promise<{ success: boolean; data: GraphTask }> {
  const { data } = await api.get(`/graph/task/${taskId}`)
  return data
}

export async function getGraphData(graphId: string): Promise<{ success: boolean; data: GraphDataResponse }> {
  const { data } = await api.get(`/graph/data/${graphId}`)
  return data
}

export async function getProject(projectId: string): Promise<{ success: boolean; data: any }> {
  const { data } = await api.get(`/graph/project/${projectId}`)
  return data
}

export async function getTaskStatus(taskId: string): Promise<{ success: boolean; data: GraphTask }> {
  const { data } = await api.get(`/graph/task/${taskId}`)
  return data
}

// ---- WebSocket ----

export function connectTaskWs(taskId: string, onMessage: (data: any) => void, onClose?: () => void): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${proto}//${window.location.host}/api/simulation/ws/${taskId}`)
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      onMessage(msg)
    } catch { /* ignore */ }
  }
  ws.onclose = () => onClose?.()
  ws.onerror = () => onClose?.()
  return ws
}
