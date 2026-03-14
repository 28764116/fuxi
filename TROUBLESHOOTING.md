# 故障排查指南

## 问题：实时渲染不工作

### 症状
- 上传文档后，图谱不显示
- 前端显示"实时分析中"但没有实体出现

### 诊断步骤

#### 1. 检查后端服务状态
```bash
ps aux | grep -E "uvicorn|celery"
```

**预期输出**：应该看到 uvicorn 和 celery 进程

**如果没有输出**：后端没有运行，执行：
```bash
cd /Users/yangboxiao/Documents/Code/github/fuxi
./start-dev.sh
```

#### 2. 检查 Neo4j 状态
```bash
# 方法1：检查端口
lsof -i :7687

# 方法2：测试连接
cd backend
python3 test_neo4j.py
```

**如果 Neo4j 没运行**：
```bash
# Docker 方式
docker start neo4j

# 或重新创建
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:latest
```

#### 3. 检查配置
```bash
# 查看 .env 文件
cat backend/.env | grep NEO4J
```

**必须配置**：
```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password  # ⚠️ 必须设置
NEO4J_DATABASE=neo4j
```

#### 4. 测试 API
```bash
# 测试实体 API
curl "http://localhost:8000/api/memory/entities?group_id=test&limit=5"

# 测试边 API
curl "http://localhost:8000/api/memory/edges?group_id=test&limit=5"
```

**预期输出**：JSON 数组（可能为空）

**如果 404**：后端路由有问题
**如果 500**：Neo4j 连接失败

#### 5. 查看日志
```bash
# 后端日志
tail -f backend/logs/app.log

# Celery 日志
tail -f backend/celery.log
```

**关键错误信息**：
- `NEO4J_PASSWORD 未配置` → 检查 .env
- `Failed to establish connection` → Neo4j 未运行
- `Triplet extraction failed` → LLM API 问题

### 常见问题修复

#### Q1: "实体数量一直是 0"
**原因**：数据写入 Neo4j 失败

**修复**：
```bash
# 1. 检查 Neo4j 日志
docker logs neo4j | tail -20

# 2. 重启 Neo4j
docker restart neo4j

# 3. 清空数据重试
# 在 Neo4j Browser (http://localhost:7474) 执行：
MATCH (n) DETACH DELETE n
```

#### Q2: "前端一直轮询，没有停止"
**原因**：后端处理慢或卡住

**修复**：
```bash
# 1. 查看 Celery 任务状态
cd backend
python3 -c "
from worker import celery_app
inspect = celery_app.control.inspect()
print('Active tasks:', inspect.active())
print('Reserved tasks:', inspect.reserved())
"

# 2. 清理卡住的任务
python3 clear_tasks.py

# 3. 重启 Celery
pkill -9 -f "celery -A worker"
cd backend
celery -A worker worker --loglevel=info --concurrency=1 &
```

#### Q3: "JSON 解析错误"
**原因**：LLM 返回格式不正确

**修复**：
- 已添加 4 层 JSON 容错
- 已启用 `response_format={"type": "json_object"}`
- 如果还有问题，检查 LLM API 配额

#### Q4: "数据库连接失败"
**PostgreSQL**:
```bash
# 测试连接
psql -U postgres -d fuxi -c "SELECT 1"

# 重启
brew services restart postgresql
```

**Neo4j**:
```bash
# 测试连接
cd backend
python3 test_neo4j.py
```

### 完整重启流程

如果以上都不行，执行完整重启：

```bash
# 1. 停止所有服务
pkill -9 -f "uvicorn"
pkill -9 -f "celery"
docker stop neo4j

# 2. 启动 Neo4j
docker start neo4j
# 等待 5 秒让 Neo4j 完全启动
sleep 5

# 3. 启动后端
cd /Users/yangboxiao/Documents/Code/github/fuxi
./start-dev.sh

# 4. 验证
curl http://localhost:8000/api/memory/entities?group_id=test
```

### 实时渲染工作原理

```
1. 用户上传文档
   ↓
2. Celery 后台任务处理（process_document）
   - 解析文档 → 分块
   - 每块提取实体/关系 → 写入 Neo4j
   ↓
3. 前端轮询（每 1.5 秒）
   - GET /api/memory/entities?group_id=xxx
   - GET /api/memory/edges?group_id=xxx
   ↓
4. 检测到新实体 → 立即更新图谱
   ↓
5. 连续 3 次无变化 → 停止轮询
```

### 调试技巧

**浏览器控制台**：
```javascript
// 检查是否有 API 错误
// F12 → Console → 查找红色错误

// 手动触发刷新
refreshGraph()
```

**后端调试**：
```python
# 在 neo4j_service.py 添加日志
logger.info(f"Writing entity: {name}, type: {entity_type}")
logger.info(f"Query returned {len(entities)} entities")
```

**Neo4j 查询**：
```cypher
// 检查数据
MATCH (g:Graph) RETURN g, count{(g)<-[:BELONGS_TO]-()} as entity_count

// 查看最近创建的实体
MATCH (n:Entity)
RETURN n
ORDER BY n.created_at DESC
LIMIT 10
```
