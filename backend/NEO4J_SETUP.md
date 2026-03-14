# Neo4j 迁移完成指南

## ✅ 已完成的迁移

### 代码层面
1. **memory/neo4j_service.py** - Neo4j 图谱服务（参考 MiroFish）
   - `temporal_upsert()`: 时序关系写入
   - `get_all_entities()`: 查询所有实体
   - `get_all_edges()`: 查询所有边

2. **memory/tasks.py** - 使用 Neo4j
   - `process_document`: 写入 Neo4j（Episodes 仍在 PostgreSQL）
   - `process_episode`: 写入 Neo4j

3. **memory/router.py** - API 从 Neo4j 查询
   - `GET /entities`: 从 Neo4j 读取
   - `GET /edges`: 从 Neo4j 读取

### 架构变更
```
之前（All PostgreSQL）:
  - Episodes (PostgreSQL)
  - Entities (PostgreSQL)
  - EntityEdges (PostgreSQL)

现在（Hybrid）:
  - Episodes (PostgreSQL) ← 保留文本存储
  - Entities (Neo4j)
  - Relationships (Neo4j) ← 支持 temporal 语义
```

## 🚀 启动步骤

### 1. 启动 Neo4j
```bash
# 使用 Docker
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:latest

# 或者本地安装
neo4j start
```

### 2. 配置环境变量
编辑 `backend/.env`:
```env
# Neo4j 配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j

# PostgreSQL 配置（Episodes 仍需要）
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=fuxi
```

### 3. 重启服务
```bash
cd /Users/yangboxiao/Documents/Code/github/fuxi
./start-dev.sh
```

### 4. 验证
访问 Neo4j Browser: http://localhost:7474
- 用户名: `neo4j`
- 密码: `your_password`

查询语句验证：
```cypher
// 查看所有 Graph
MATCH (g:Graph) RETURN g

// 查看所有实体
MATCH (n:Entity) RETURN n LIMIT 25

// 查看所有关系
MATCH (a)-[r:RELATES]->(b) RETURN a, r, b LIMIT 25

// 查看活跃关系
MATCH (a)-[r:RELATES]->(b)
WHERE r.expired_at IS NULL
RETURN a.name, r.name, b.name
```

## 📊 数据迁移（可选）

如果你有现有 PostgreSQL 数据需要迁移到 Neo4j：

```bash
cd backend
python3 migrate_to_neo4j.py --group-id <your_group_id>
```

（迁移脚本待实现）

## 🔍 对比 MiroFish

### 相似点 ✅
- Neo4j 存储实体和关系
- PostgreSQL + pgvector 存储 embeddings
- 增量写入逻辑
- 实体去重

### 差异点 ⚠️
- **Temporal 语义**: 我们保留了 `valid_at` / `expired_at` 字段
- **Episode 追踪**: 我们的 `episode_ids` 数组记录来源
- **冲突检测**: 简化版（未实现 LLM 冲突判断）

## 🐛 故障排查

### Neo4j 连接失败
```python
# 检查配置
from app.config import settings
print(settings.neo4j_uri)
print(settings.neo4j_password)

# 测试连接
from neo4j import GraphDatabase
driver = GraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_username, settings.neo4j_password)
)
driver.verify_connectivity()
```

### 数据不显示
1. 确认 Neo4j 中有 Graph 节点：
   ```cypher
   MATCH (g:Graph) RETURN g
   ```

2. 检查实体和边：
   ```cypher
   MATCH (n:Entity) RETURN count(n)
   MATCH ()-[r:RELATES]->() RETURN count(r)
   ```

3. 查看日志：
   ```bash
   tail -f backend/logs/app.log
   ```

## 📈 性能优化

### Neo4j 索引
```cypher
// 实体名称索引
CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)

// UUID 索引
CREATE INDEX entity_uuid IF NOT EXISTS FOR (n:Entity) ON (n.uuid)

// Temporal 索引
CREATE INDEX relationship_temporal IF NOT EXISTS FOR ()-[r:RELATES]-() ON (r.expired_at)
```

### 查询优化
```cypher
// 使用 LIMIT 避免全图扫描
MATCH (n:Entity) RETURN n LIMIT 100

// 过滤活跃关系
MATCH (a)-[r:RELATES]->(b)
WHERE r.expired_at IS NULL
RETURN a, r, b
```

## 下一步

- [ ] 实现数据迁移脚本
- [ ] 添加 LLM 冲突检测（参考 MiroFish temporal.py）
- [ ] 实体摘要更新（从 Neo4j 聚合）
- [ ] 性能测试和优化
