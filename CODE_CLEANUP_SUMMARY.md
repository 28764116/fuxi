# 代码清理总结 (Code Cleanup Summary)

**日期**: 2026-03-14
**目标**: 移除 PostgreSQL → Neo4j 迁移后的冗余代码

---

## ✅ 已完成清理

### 1. 标记废弃的数据模型

**文件**: `backend/memory/models.py`

- `Entity` 类：添加 DEPRECATED 说明，数据已迁移到 Neo4j
- `EntityEdge` 类：添加 DEPRECATED 说明，数据已迁移到 Neo4j
- **保留原因**：向后兼容和迁移脚本使用

**建议**：未来可删除这些表定义（Episodes 除外）

---

### 2. 标记废弃的服务函数

**文件**: `backend/memory/service.py`

| 函数 | 状态 | 替代方案 |
|-----|------|---------|
| `_normalize_entity_name()` | ❌ 已删除 | Neo4j 内部处理 |
| `get_or_create_entity()` | ❌ 已删除 | `Neo4jGraphService.get_or_create_entity()` |
| `search_entities()` | ⚠️ 标记为 DEPRECATED | TODO: Neo4j 向量搜索 |
| `search_edges()` | ⚠️ 标记为 DEPRECATED | TODO: Neo4j 向量搜索 |
| `get_entity_facts()` | ⚠️ 标记为 DEPRECATED | `Neo4jGraphService.get_all_edges()` |
| `get_entity_facts_at()` | ⚠️ 标记为 DEPRECATED | TODO: Neo4j 时间旅行查询 |

**警告**：标记为 DEPRECATED 的函数仍被调用，但会返回空结果（PostgreSQL 表已空）

---

### 3. 禁用冗余的 API 端点

**文件**: `backend/memory/router.py`

#### 已注释掉（不再可用）：
- `GET /entities/{entity_id}` - 查询单个实体（PostgreSQL）
- `GET /entities/{entity_id}/edges` - 查询实体关系（PostgreSQL）
- `GET /facts/{entity_id}` - 查询实体事实（PostgreSQL）
- `GET /facts/{entity_id}/at` - 时间旅行查询（PostgreSQL）

#### 标记为 TODO（仍可用但需迁移）：
- `GET /search` - 语义搜索关系（需实现 Neo4j 向量搜索）
- `GET /search/entities` - 语义搜索实体（需实现 Neo4j 向量搜索）

**建议**：实现 Neo4j 向量搜索后重写这些端点

---

### 4. 简化前端数据格式

**文件**: `frontend/src/components/GraphView.vue`

**清理前**（支持两种格式）：
```typescript
interface Entity { id: string; ... }           // 旧格式
interface GraphNode { uuid: string; ... }      // 新格式
const props = defineProps<{
  entities: (Entity | GraphNode)[]  // 联合类型
  edges: (EntityEdge | GraphEdge)[]
}>()

// 兼容逻辑遍布代码
const id = e.uuid || e.id
const sourceId = e.source_node_uuid || e.source_entity_id
```

**清理后**（仅 Neo4j 格式）：
```typescript
interface Entity {
  id: string  // UUID from Neo4j
  name: string
  entity_type: string
  ...
}
interface EntityEdge {
  id: string
  source_entity_id: string
  target_entity_id: string
  predicate: string
  ...
}
const props = defineProps<{
  entities: Entity[]  // 单一类型
  edges: EntityEdge[]
}>()

// 直接访问，无需兼容逻辑
const id = e.id
const sourceId = e.source_entity_id
```

**收益**：
- 代码更简洁（减少 ~30 行兼容逻辑）
- 类型安全（移除联合类型）
- 维护更容易（单一数据源）

---

### 5. 其他优化

**文件**: `frontend/src/views/LiveGraphBuilder.vue`
- 修复 `.control-panel` 布局问题：`height: 140px` → `min-height: 140px`
- 避免进度条内容溢出导致空白块

**文件**: `backend/memory/extractor.py`
- 强化 prompt：要求 entity name 也遵循 `{language}` 参数
- 修复中英文混搭问题（"Trump" vs "特朗普"）

---

## 📊 清理统计

| 分类 | 文件数 | 代码行数 | 状态 |
|------|--------|---------|------|
| 标记 DEPRECATED 的模型 | 1 | ~150 | ✅ 完成 |
| 删除的冗余函数 | 1 | ~80 | ✅ 完成 |
| 标记 DEPRECATED 的函数 | 1 | ~120 | ⚠️ 仍被调用 |
| 禁用的 API 端点 | 1 | ~60 | ✅ 完成 |
| 简化的前端代码 | 1 | ~30 | ✅ 完成 |
| **总计** | **5** | **~440** | - |

---

## ⚠️ 待办事项 (TODO)

### 高优先级
1. **实现 Neo4j 向量搜索**
   - 迁移 `search_entities()` 和 `search_edges()` 到 Neo4j
   - 在 Neo4j 中存储 embeddings（node.summary_embedding、edge.fact_embedding）
   - 重写 `/search` 和 `/search/entities` 端点

2. **实现 Neo4j 时间旅行查询**
   - 迁移 `get_entity_facts_at()` 逻辑到 Neo4j Cypher
   - 支持 `valid_at <= T AND (expired_at IS NULL OR expired_at > T)` 查询

### 低优先级
3. **完全删除 PostgreSQL 实体表**
   - 确认所有迁移脚本完成后，删除 `entities` 和 `entity_edges` 表定义
   - 删除 `memory/models.py` 中的 `Entity` 和 `EntityEdge` 类
   - 删除 `memory/schemas.py` 中的 `EntityResponse` 和 `EntityEdgeResponse`

4. **清理未使用的导入**
   - 检查并移除对 `Entity` 和 `EntityEdge` 的导入（除 Episode 相关代码）

---

## 🔍 已知影响

### API 变更
- ❌ **中断**：`GET /entities/{id}`、`/facts/{id}` 等端点已禁用
- ⚠️ **降级**：`/search` 端点可能返回空结果（需 Neo4j 向量搜索）

### 前端兼容性
- ✅ **无影响**：前端已统一为 Neo4j 数据格式，与后端完全兼容

### 数据库
- ✅ **无影响**：PostgreSQL `episodes` 表仍正常使用
- ⚠️ **空表**：`entities` 和 `entity_edges` 表已空（数据在 Neo4j）

---

## 🚀 验证步骤

1. **重启服务**：
   ```bash
   pkill -9 -f "uvicorn|celery"
   cd /Users/yangboxiao/Documents/Code/github/fuxi
   ./start-dev.sh
   ```

2. **测试核心功能**：
   ```bash
   # 测试实体查询（Neo4j）
   curl "http://localhost:8000/api/memory/entities?group_id=test&limit=5"

   # 测试边查询（Neo4j）
   curl "http://localhost:8000/api/memory/edges?group_id=test&limit=5"
   ```

3. **上传文档测试实时渲染**：
   - 访问 http://localhost:5173
   - 上传文档，观察图谱实时更新
   - 确认 entity name 语言统一（中文文档 → 中文名）

---

## 📝 迁移记录

- **NEO4J_MIGRATION.md**：完整迁移计划
- **NEO4J_SETUP.md**：Neo4j 安装配置
- **TROUBLESHOOTING.md**：故障排查指南

---

## 总结

本次清理主要针对 PostgreSQL → Neo4j 迁移后的遗留代码：

✅ **已清理**：~440 行冗余代码标记或删除
⚠️ **待完成**：向量搜索和时间旅行查询迁移
🎯 **收益**：代码更清晰、维护更容易、单一数据源

**下一步**：实现 Neo4j 向量搜索，彻底移除 PostgreSQL 依赖。
