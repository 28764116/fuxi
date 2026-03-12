import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export interface Entity {
  id: string
  group_id: string
  name: string
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

export async function uploadFile(groupId: string, threadId: string, file: File): Promise<Episode[]> {
  const form = new FormData()
  form.append('group_id', groupId)
  form.append('thread_id', threadId)
  form.append('file', file)
  const { data } = await api.post('/memory/upload', form)
  return data
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
  // Fetch edges for all entities
  const entities = await getEntities(groupId)
  const edgeMap = new Map<string, EntityEdge>()
  for (const entity of entities) {
    const edges = await getEntityEdges(entity.id)
    for (const e of edges) {
      edgeMap.set(e.id, e)
    }
  }
  return Array.from(edgeMap.values())
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
