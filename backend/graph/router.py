"""
图谱 API 路由
包含完整的图谱构建功能：文件上传、本体生成、图谱构建、向量搜索
"""
import os
import re
import uuid
import logging
import threading
from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from .service import GraphService
from .ontology import OntologyGenerator
from .vector_store import get_vector_store
from app.config import settings
from app.auth import require_api_key

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/graph", tags=["graph"], dependencies=[Depends(require_api_key)])


class ProjectStatus(str, Enum):
    """项目状态"""
    CREATED = "created"
    ONTOLOGY_GENERATED = "ontology_generated"
    GRAPH_BUILDING = "graph_building"
    GRAPH_COMPLETED = "graph_completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# 内存存储（生产环境应使用数据库）
_lock = threading.Lock()
_projects: dict = {}
_tasks: dict = {}


def allowed_file(filename: str) -> bool:
    """检查文件是否允许上传"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in settings.allowed_extensions


def preprocess_text(text: str) -> str:
    """预处理文本"""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join(lines).strip()


def extract_text_from_file(file: UploadFile) -> str:
    """从上传文件提取文本"""
    import fitz
    import io
    
    content = file.file.read()
    
    if file.filename.lower().endswith('.pdf'):
        doc = fitz.open(stream=io.BytesIO(content), filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    else:
        try:
            return content.decode('utf-8')
        except:
            return content.decode('gbk', errors='ignore')


# ============= 项目管理接口 =============

@router.get("/project/{project_id}")
async def get_project(project_id: str):
    """获取项目"""
    project = _projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
    return {"success": True, "data": project}


@router.get("/project/list")
async def list_projects(limit: int = 50):
    """列出项目"""
    projects = list(_projects.values())[:limit]
    return {"success": True, "data": projects, "count": len(projects)}


@router.delete("/project/{project_id}")
async def delete_project(project_id: str):
    """删除项目"""
    if project_id not in _projects:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
    
    project = _projects[project_id]
    
    if project.get("graph_id"):
        service = GraphService()
        try:
            service.delete_graph(project["graph_id"])
        except:
            pass
        vector_store = get_vector_store()
        if vector_store:
            try:
                vector_store.delete_by_graph_id(project["graph_id"])
            except:
                pass
    
    del _projects[project_id]
    return {"success": True, "message": f"项目已删除: {project_id}"}


@router.post("/project/{project_id}/reset")
async def reset_project(project_id: str):
    """重置项目"""
    project = _projects.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
    
    project["status"] = ProjectStatus.ONTOLOGY_GENERATED.value if project.get("ontology") else ProjectStatus.CREATED.value
    project["graph_id"] = None
    project["graph_build_task_id"] = None
    project["error"] = None
    
    return {"success": True, "message": f"项目已重置: {project_id}", "data": project}


# ============= 接口1：上传文件并生成本体 =============

@router.post("/ontology/generate")
async def generate_ontology(
    files: List[UploadFile] = File(...),
    simulation_requirement: str = Form(...),
    project_name: str = Form("Fuxi Project"),
    additional_context: str = Form("")
):
    """
    接口1：上传文件，异步生成本体定义
    立即返回 project_id + task_id，通过 /graph/task/{task_id} 轮询进度
    """
    if not files or all(not f.filename for f in files):
        raise HTTPException(status_code=400, detail="请至少上传一个文档文件")

    if not simulation_requirement:
        raise HTTPException(status_code=400, detail="请提供 simulation_requirement")

    project_id = f"proj_{uuid.uuid4().hex[:12]}"
    task_id = f"task_{uuid.uuid4().hex[:12]}"

    document_texts = []
    all_text = ""
    file_info = []

    for file in files:
        if file and file.filename and allowed_file(file.filename):
            try:
                text = extract_text_from_file(file)
                text = preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file.filename} ===\n{text}"
                file_info.append({"filename": file.filename, "size": 0})
            except Exception as e:
                logger.warning("处理文件失败 %s: %s", file.filename, e)

    if not document_texts:
        raise HTTPException(status_code=400, detail="没有成功处理任何文档")

    _projects[project_id] = {
        "project_id": project_id,
        "name": project_name,
        "simulation_requirement": simulation_requirement,
        "additional_context": additional_context,
        "text": all_text,
        "files": file_info,
        "total_text_length": len(all_text),
        "ontology": None,
        "analysis_summary": None,
        "status": ProjectStatus.CREATED.value,
        "graph_id": None,
        "graph_build_task_id": None,
        "ontology_task_id": task_id,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    _tasks[task_id] = {
        "task_id": task_id,
        "type": "ontology_generate",
        "status": TaskStatus.PROCESSING.value,
        "message": "正在分析文档，生成本体定义...",
        "progress": 10,
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    def ontology_task():
        try:
            with _lock:
                _tasks[task_id]["message"] = "正在调用 LLM 分析文档..."
                _tasks[task_id]["progress"] = 30
                _tasks[task_id]["updated_at"] = datetime.now().isoformat()

            generator = OntologyGenerator()
            ontology = generator.generate(
                document_texts=document_texts,
                simulation_requirement=simulation_requirement,
                additional_context=additional_context if additional_context else None
            )

            with _lock:
                _projects[project_id]["ontology"] = {
                    "entity_types": ontology.get("entity_types", []),
                    "edge_types": ontology.get("edge_types", [])
                }
                _projects[project_id]["analysis_summary"] = ontology.get("analysis_summary", "")
                _projects[project_id]["status"] = ProjectStatus.ONTOLOGY_GENERATED.value
                _projects[project_id]["updated_at"] = datetime.now().isoformat()

                _tasks[task_id]["status"] = TaskStatus.COMPLETED.value
                _tasks[task_id]["message"] = "本体生成完成"
                _tasks[task_id]["progress"] = 100
                _tasks[task_id]["result"] = {
                    "project_id": project_id,
                    "project_name": project_name,
                    "ontology": _projects[project_id]["ontology"],
                    "analysis_summary": _projects[project_id]["analysis_summary"],
                    "files": file_info,
                    "total_text_length": len(all_text)
                }
        except Exception as e:
            logger.exception("本体生成失败")
            with _lock:
                _projects[project_id]["status"] = ProjectStatus.FAILED.value
                _projects[project_id]["error"] = str(e)
                _tasks[task_id]["status"] = TaskStatus.FAILED.value
                _tasks[task_id]["message"] = f"本体生成失败: {str(e)}"
                _tasks[task_id]["error"] = str(e)

        with _lock:
            _tasks[task_id]["updated_at"] = datetime.now().isoformat()

    thread = threading.Thread(target=ontology_task, daemon=True)
    thread.start()

    return {
        "success": True,
        "data": {
            "project_id": project_id,
            "task_id": task_id,
            "message": "本体生成任务已启动，请通过 /graph/task/{task_id} 查询进度"
        }
    }


class OntologyGenerateRequest(BaseModel):
    simulation_requirement: str
    project_name: Optional[str] = "Fuxi Project"
    additional_context: Optional[str] = None


@router.post("/ontology/generate/text")
async def generate_ontology_from_text(request: OntologyGenerateRequest):
    """接口1（纯文本版本）：直接传入文本，异步生成本体定义"""
    project_id = f"proj_{uuid.uuid4().hex[:12]}"
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    document_texts = [request.simulation_requirement]

    _projects[project_id] = {
        "project_id": project_id,
        "name": request.project_name,
        "simulation_requirement": request.simulation_requirement,
        "additional_context": request.additional_context,
        "text": request.simulation_requirement,
        "files": [],
        "total_text_length": len(request.simulation_requirement),
        "ontology": None,
        "analysis_summary": None,
        "status": ProjectStatus.CREATED.value,
        "graph_id": None,
        "graph_build_task_id": None,
        "ontology_task_id": task_id,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    _tasks[task_id] = {
        "task_id": task_id,
        "type": "ontology_generate",
        "status": TaskStatus.PROCESSING.value,
        "message": "正在分析文本，生成本体定义...",
        "progress": 10,
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    def ontology_task():
        try:
            with _lock:
                _tasks[task_id]["message"] = "正在调用 LLM 分析文本..."
                _tasks[task_id]["progress"] = 30
                _tasks[task_id]["updated_at"] = datetime.now().isoformat()

            generator = OntologyGenerator()
            ontology = generator.generate(
                document_texts=document_texts,
                simulation_requirement=request.simulation_requirement,
                additional_context=request.additional_context
            )

            with _lock:
                _projects[project_id]["ontology"] = {
                    "entity_types": ontology.get("entity_types", []),
                    "edge_types": ontology.get("edge_types", [])
                }
                _projects[project_id]["analysis_summary"] = ontology.get("analysis_summary", "")
                _projects[project_id]["status"] = ProjectStatus.ONTOLOGY_GENERATED.value
                _projects[project_id]["updated_at"] = datetime.now().isoformat()

                _tasks[task_id]["status"] = TaskStatus.COMPLETED.value
                _tasks[task_id]["message"] = "本体生成完成"
                _tasks[task_id]["progress"] = 100
                _tasks[task_id]["result"] = {
                    "project_id": project_id,
                    "project_name": request.project_name,
                    "ontology": _projects[project_id]["ontology"],
                    "analysis_summary": _projects[project_id]["analysis_summary"]
                }
        except Exception as e:
            logger.exception("本体生成失败")
            with _lock:
                _projects[project_id]["status"] = ProjectStatus.FAILED.value
                _projects[project_id]["error"] = str(e)
                _tasks[task_id]["status"] = TaskStatus.FAILED.value
                _tasks[task_id]["message"] = f"本体生成失败: {str(e)}"
                _tasks[task_id]["error"] = str(e)

        with _lock:
            _tasks[task_id]["updated_at"] = datetime.now().isoformat()

    thread = threading.Thread(target=ontology_task, daemon=True)
    thread.start()

    return {
        "success": True,
        "data": {
            "project_id": project_id,
            "task_id": task_id,
            "message": "本体生成任务已启动，请通过 /graph/task/{task_id} 查询进度"
        }
    }


# ============= 接口2：构建图谱 =============

class BuildGraphRequest(BaseModel):
    project_id: str
    graph_name: Optional[str] = None
    chunk_size: Optional[int] = settings.default_chunk_size
    chunk_overlap: Optional[int] = settings.default_chunk_overlap
    force: Optional[bool] = False


@router.post("/build")
async def build_graph(request: BuildGraphRequest):
    """接口2：根据 project_id 构建图谱"""
    project = _projects.get(request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目不存在: {request.project_id}")
    
    if project["status"] == ProjectStatus.CREATED.value:
        raise HTTPException(status_code=400, detail="项目尚未生成本体，请先调用 /ontology/generate")
    
    if project["status"] == ProjectStatus.GRAPH_BUILDING.value and not request.force:
        raise HTTPException(status_code=400, detail="图谱正在构建中，如需强制重建请添加 force: true")
    
    if request.force and project["status"] in [ProjectStatus.GRAPH_BUILDING.value, ProjectStatus.FAILED.value, ProjectStatus.GRAPH_COMPLETED.value]:
        if project.get("graph_id"):
            service = GraphService()
            try:
                service.delete_graph(project["graph_id"])
            except:
                pass
            vector_store = get_vector_store()
            if vector_store:
                try:
                    vector_store.delete_by_graph_id(project["graph_id"])
                except:
                    pass
        project["status"] = ProjectStatus.ONTOLOGY_GENERATED.value
        project["graph_id"] = None
        project["graph_build_task_id"] = None
        project["error"] = None
    
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    graph_id = f"graph_{uuid.uuid4().hex[:12]}"
    
    _tasks[task_id] = {
        "task_id": task_id,
        "status": TaskStatus.PROCESSING.value,
        "message": "图谱构建中...",
        "progress": 0,
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "graph_id": graph_id
    }
    
    project["status"] = ProjectStatus.GRAPH_BUILDING.value
    project["graph_id"] = graph_id
    project["graph_build_task_id"] = task_id
    project["updated_at"] = datetime.now().isoformat()
    
    def build_task():
        service = GraphService()
        try:
            service.create_graph(request.graph_name or project["name"], graph_id=graph_id)

            def progress_callback(msg: str, ratio: float):
                with _lock:
                    _tasks[task_id]["message"] = msg
                    _tasks[task_id]["progress"] = int(ratio * 100)
                    _tasks[task_id]["updated_at"] = datetime.now().isoformat()

            service.build_graph(
                graph_id=graph_id,
                text=project["text"],
                ontology=project["ontology"],
                chunk_size=request.chunk_size,
                overlap=request.chunk_overlap,
                max_workers=8,
                progress_callback=progress_callback
            )

            graph_data = service.get_graph_data(graph_id)

            with _lock:
                _tasks[task_id]["status"] = TaskStatus.COMPLETED.value
                _tasks[task_id]["message"] = "图谱构建完成"
                _tasks[task_id]["progress"] = 100
                _tasks[task_id]["result"] = {
                    "project_id": request.project_id,
                    "graph_id": graph_id,
                    "node_count": graph_data["node_count"],
                    "edge_count": graph_data["edge_count"]
                }
                project["status"] = ProjectStatus.GRAPH_COMPLETED.value

        except Exception as e:
            logger.exception("图谱构建失败")
            with _lock:
                _tasks[task_id]["status"] = TaskStatus.FAILED.value
                _tasks[task_id]["message"] = f"构建失败: {str(e)}"
                _tasks[task_id]["error"] = str(e)
                project["status"] = ProjectStatus.FAILED.value
                project["error"] = str(e)

        with _lock:
            _tasks[task_id]["updated_at"] = datetime.now().isoformat()
            project["updated_at"] = datetime.now().isoformat()
    
    thread = threading.Thread(target=build_task, daemon=True)
    thread.start()
    
    return {
        "success": True,
        "data": {
            "project_id": request.project_id,
            "task_id": task_id,
            "message": "图谱构建任务已启动，请通过 /graph/task/{task_id} 查询进度"
        }
    }


# ============= 任务查询接口 =============

@router.get("/task/{task_id}")
async def get_task(task_id: str):
    """获取任务状态"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return {"success": True, "data": task}


@router.get("/tasks")
async def list_tasks():
    """列出所有任务"""
    return {"success": True, "data": list(_tasks.values()), "count": len(_tasks)}


# ============= 图谱数据接口 =============

@router.get("/data/{graph_id}")
async def get_graph_data(graph_id: str):
    """获取图谱数据"""
    service = GraphService()
    try:
        data = service.get_graph_data(graph_id)
        return {"success": True, "data": data}
    except Exception as e:
        logger.exception("获取图谱数据失败: %s", graph_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/{graph_id}")
async def search_graph(graph_id: str, q: str = "", limit: int = 10):
    """关键词 + 向量混合搜索"""
    if not q:
        raise HTTPException(status_code=400, detail="请提供搜索关键词 ?q=...")
    
    service = GraphService()
    vector_store = get_vector_store()
    
    try:
        keyword_results = service.neo4j.search_nodes(graph_id, q, limit=limit)
    except Exception as e:
        keyword_results = []
    
    vector_results = []
    if vector_store:
        try:
            vector_results = vector_store.search(graph_id, q, limit=limit)
            vector_results = [
                {"uuid": r.uuid, "content": r.content, "metadata": r.metadata, "score": r.score}
                for r in vector_results
            ]
        except Exception as e:
            pass
    
    return {
        "success": True,
        "data": {
            "keyword_results": [n.to_dict() for n in keyword_results],
            "vector_results": vector_results
        }
    }


@router.delete("/graph/{graph_id}")
async def delete_graph(graph_id: str):
    """删除图谱"""
    service = GraphService()
    try:
        service.delete_graph(graph_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    vector_store = get_vector_store()
    if vector_store:
        try:
            vector_store.delete_by_graph_id(graph_id)
        except:
            pass
    
    return {"success": True, "message": f"图谱已删除: {graph_id}"}
