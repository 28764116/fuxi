# Neo4j 迁移计划

## 当前架构
```
PostgreSQL:
- Episodes (文本内容 + embedding)
- Entities (实体 + summary_embedding)
- EntityEdges (关系 + fact_embedding + temporal fields)

graph/ 模块:
- Neo4j 基础客户端（未启用）
- 缺少 temporal 支持
```

## 目标架构（参考 MiroFish）
```
PostgreSQL + pgvector:
- Episodes (保留，用于文本存储和向量搜索)
- vector_store (embedding 存储)

Neo4j:
- Entities (节点 + labels + summary)
- Relationships (边 + fact + valid_at + expired_at + episode_ids)
  - 支持 temporal 语义（时序事实管理）
  - 支持多对多关系（curved edges）
```

## 迁移步骤

### Phase 1: 扩展 Neo4j 客户端
- [x] 检查现有 graph/client.py
- [ ] 添加 temporal 字段支持（valid_at, expired_at）
- [ ] 添加 episode_ids 数组字段
- [ ] 实现 temporal_upsert 逻辑（冲突检测 + 过期）

### Phase 2: 创建新的 Neo4j service 层
- [ ] memory/neo4j_service.py: 实体/关系 CRUD
- [ ] memory/neo4j_temporal.py: temporal upsert + 冲突检测
- [ ] 保留 memory/service.py 中的 Episode 操作（仍用 PostgreSQL）

### Phase 3: 更新 tasks.py
- [ ] process_document: 使用 Neo4j 存储实体/关系
- [ ] process_episode: 使用 Neo4j 存储三元组
- [ ] 保留 embedding 生成和向量存储（PostgreSQL）

### Phase 4: 更新 router.py
- [ ] GET /entities: 从 Neo4j 查询
- [ ] GET /edges: 从 Neo4j 查询
- [ ] 保持 API 响应格式不变

### Phase 5: 数据迁移脚本
- [ ] 从 PostgreSQL entities/entity_edges 迁移到 Neo4j
- [ ] 保留 episodes 表不动

### Phase 6: 测试验证
- [ ] 单元测试
- [ ] 集成测试
- [ ] 性能对比

## 关键设计决策

1. **双数据库模式**
   - PostgreSQL: Episodes + embeddings（向量搜索）
   - Neo4j: Entities + Relationships（图遍历）

2. **Temporal 语义保留**
   - 关系属性：valid_at, expired_at, episode_ids
   - 冲突检测：LLM 判断是否矛盾
   - 过期策略：expired_at 标记，不删除

3. **去重策略**
   - 实体：按 (group_id, name) 去重
   - 关系：按 (source, target, predicate, expired_at IS NULL) 唯一约束

4. **向量存储**
   - PostgreSQL pgvector 保留
   - Neo4j 不存储 embedding（只存 fact 文本）

## 性能优化

1. **Neo4j 索引**
   ```cypher
   CREATE INDEX entity_name FOR (n:Entity) ON (n.name)
   CREATE INDEX entity_uuid FOR (n:Entity) ON (n.uuid)
   CREATE INDEX relationship_temporal FOR ()-[r:RELATES]-() ON (r.expired_at)
   ```

2. **批量写入**
   - 使用 `UNWIND` 批量创建节点
   - 关系分批创建（避免内存溢出）

3. **查询优化**
   - 使用 `MATCH` + `WHERE expired_at IS NULL` 查询活跃关系
   - 限制遍历深度避免全图扫描
