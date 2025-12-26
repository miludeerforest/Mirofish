"""
FalkorDB 知识图谱适配器

基于 FalkorDB 原生库实现，提供与 ZepEntityReader / GraphBuilderService 兼容的接口。
使用 OpenAI API 进行实体和关系提取。

注意：由于 graphiti-core 与 camel-oasis 的 neo4j 版本冲突，
本实现使用 FalkorDB 原生库 + OpenAI API 直接实现图谱功能。
"""

import asyncio
import uuid
import time
import threading
import json
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from falkordb import FalkorDB

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from .text_processor import TextProcessor
from ..utils.logger import get_logger

logger = get_logger('mirofish.falkordb_adapter')


def _sanitize_label(label: str) -> str:
    """
    将标签名转换为有效的 Cypher 标识符
    FalkorDB/Neo4j 的标签和关系类型只支持 ASCII 字符
    """
    import re
    import hashlib
    
    # 如果是纯 ASCII，直接清理并返回
    if label.isascii():
        # 移除非法字符，只保留字母数字下划线
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', label)
        # 确保不以数字开头
        if sanitized and sanitized[0].isdigit():
            sanitized = 'T_' + sanitized
        return sanitized or 'Entity'
    
    # 对于中文等非 ASCII 字符，生成一个基于哈希的短标识符
    # 同时保持可读性（使用首字母或拼音缩写）
    hash_suffix = hashlib.md5(label.encode()).hexdigest()[:6]
    return f"Type_{hash_suffix}"


@dataclass
class GraphInfo:
    """图谱信息"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


@dataclass
class EntityNode:
    """实体节点数据结构"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """获取实体类型（排除默认的Entity标签）"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """过滤后的实体集合"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class FalkorDBClient:
    """FalkorDB 客户端封装"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        try:
            self._db = FalkorDB(
                host=Config.FALKORDB_HOST,
                port=Config.FALKORDB_PORT
            )
            self._initialized = True
            logger.info(f"FalkorDB 连接成功: {Config.FALKORDB_HOST}:{Config.FALKORDB_PORT}")
        except Exception as e:
            logger.error(f"FalkorDB 连接失败: {e}")
            raise
    
    def get_graph(self, graph_id: str):
        """获取或创建图谱"""
        return self._db.select_graph(graph_id)
    
    def execute_query(self, graph_id: str, query: str, params: Dict = None):
        """执行 Cypher 查询"""
        graph = self.get_graph(graph_id)
        return graph.query(query, params or {})


def _get_falkordb_client() -> FalkorDBClient:
    """获取 FalkorDB 客户端单例"""
    return FalkorDBClient()


def _get_openai_client() -> OpenAI:
    """获取 OpenAI 客户端"""
    return OpenAI(
        api_key=Config.LLM_API_KEY,
        base_url=Config.LLM_BASE_URL
    )


class EntityExtractor:
    """使用 LLM 提取实体和关系"""
    
    EXTRACTION_PROMPT = """从以下文本中提取实体和关系。

文本：
{text}

本体定义（如果有的话）：
{ontology}

请以 JSON 格式返回，包含：
1. entities: 实体列表，每个实体包含 name, type, summary, attributes
2. relations: 关系列表，每个关系包含 source, target, relation_type, fact

严格遵循以下 JSON 格式：
{{
    "entities": [
        {{"name": "实体名称", "type": "实体类型", "summary": "简短描述", "attributes": {{}}}}
    ],
    "relations": [
        {{"source": "源实体名", "target": "目标实体名", "relation_type": "关系类型", "fact": "关系的事实描述"}}
    ]
}}

只返回 JSON，不要包含任何其他文本。"""

    def __init__(self):
        self.client = _get_openai_client()
        self.model = Config.LLM_MODEL_NAME
    
    def extract(self, text: str, ontology: Dict[str, Any] = None) -> Dict[str, Any]:
        """从文本中提取实体和关系"""
        ontology_str = json.dumps(ontology, ensure_ascii=False, indent=2) if ontology else "无特定本体定义"
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的知识图谱实体关系提取助手。请严格按照 JSON 格式输出。"},
                    {"role": "user", "content": self.EXTRACTION_PROMPT.format(text=text, ontology=ontology_str)}
                ],
                temperature=0.3,
            )
            
            content = response.choices[0].message.content.strip()
            # 提取 JSON 部分
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content)
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}, 内容: {content[:200]}")
            return {"entities": [], "relations": []}
        except Exception as e:
            logger.error(f"实体提取失败: {e}")
            return {"entities": [], "relations": []}


class GraphitiGraphBuilder:
    """
    FalkorDB 版图谱构建服务
    提供与 GraphBuilderService 兼容的接口
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """初始化"""
        self._falkordb = None
        self._extractor = None
        self.task_manager = TaskManager()
        
        # 存储图谱元数据
        self._graphs: Dict[str, Dict[str, Any]] = {}
        
    @property
    def falkordb(self) -> FalkorDBClient:
        """延迟初始化 FalkorDB 客户端"""
        if self._falkordb is None:
            self._falkordb = _get_falkordb_client()
        return self._falkordb
    
    @property
    def extractor(self) -> EntityExtractor:
        """延迟初始化实体提取器"""
        if self._extractor is None:
            self._extractor = EntityExtractor()
        return self._extractor
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        异步构建图谱
        
        Args:
            text: 输入文本
            ontology: 本体定义
            graph_name: 图谱名称
            chunk_size: 文本块大小
            chunk_overlap: 块重叠大小
            batch_size: 每批发送的块数量
            
        Returns:
            任务ID
        """
        # 创建任务
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
                "backend": "falkordb",
            }
        )
        
        # 在后台线程中执行构建
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """图谱构建工作线程"""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="开始构建 FalkorDB 图谱..."
            )
            
            # 1. 创建图谱
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"图谱已创建: {graph_id}"
            )
            
            # 2. 设置本体
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="本体已设置"
            )
            
            # 3. 文本分块
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"文本已分割为 {total_chunks} 个块"
            )
            
            # 4. 分批添加数据
            self.add_text_batches(
                graph_id, chunks, ontology, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.6),  # 20-80%
                    message=msg
                )
            )
            
            # 5. 获取图谱信息
            self.task_manager.update_task(
                task_id,
                progress=90,
                message="获取图谱信息..."
            )
            
            graph_info = self._get_graph_info(graph_id)
            
            # 完成
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
                "backend": "falkordb",
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            logger.error(f"FalkorDB 图谱构建失败: {error_msg}")
            self.task_manager.fail_task(task_id, error_msg)
    
    def create_graph(self, name: str) -> str:
        """创建图谱"""
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        
        # 存储图谱元数据
        self._graphs[graph_id] = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "ontology": None,
        }
        
        # 创建索引以提高查询性能
        try:
            graph = self.falkordb.get_graph(graph_id)
            # 创建节点索引
            graph.query("CREATE INDEX FOR (n:Entity) ON (n.uuid)")
            graph.query("CREATE INDEX FOR (n:Entity) ON (n.name)")
        except Exception as e:
            logger.warning(f"创建索引时出错（可能已存在）: {e}")
        
        logger.info(f"FalkorDB 图谱已创建: {graph_id} ({name})")
        return graph_id
    
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """设置图谱本体"""
        if graph_id in self._graphs:
            self._graphs[graph_id]["ontology"] = ontology
        logger.info(f"FalkorDB 本体已设置: {graph_id}")
    
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        ontology: Dict[str, Any] = None,
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """分批添加文本到图谱"""
        entity_uuids = []
        total_chunks = len(chunks)
        
        for i, chunk in enumerate(chunks):
            chunk_num = i + 1
            
            if progress_callback:
                progress = (i + 1) / total_chunks
                progress_callback(
                    f"处理第 {chunk_num}/{total_chunks} 个文本块...",
                    progress
                )
            
            try:
                # 使用 LLM 提取实体和关系
                extraction = self.extractor.extract(chunk, ontology)
                
                # 存储实体
                for entity in extraction.get("entities", []):
                    entity_uuid = self._add_entity(graph_id, entity)
                    if entity_uuid:
                        entity_uuids.append(entity_uuid)
                
                # 存储关系
                for relation in extraction.get("relations", []):
                    self._add_relation(graph_id, relation)
                
                # 避免请求过快
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"添加文本块 {chunk_num} 失败: {e}")
                if progress_callback:
                    progress_callback(f"文本块 {chunk_num} 失败: {str(e)}", 0)
        
        return entity_uuids
    
    def _add_entity(self, graph_id: str, entity: Dict[str, Any]) -> Optional[str]:
        """添加实体到图谱"""
        try:
            entity_uuid = uuid.uuid4().hex
            name = entity.get("name", "")
            entity_type = entity.get("type", "Entity")
            summary = entity.get("summary", "")
            attributes = json.dumps(entity.get("attributes", {}), ensure_ascii=False)
            
            # 先检查是否已存在同名实体
            check_query = """
            MATCH (n:Entity {name: $name})
            RETURN n.uuid AS uuid
            """
            result = self.falkordb.execute_query(graph_id, check_query, {"name": name})
            
            if result.result_set:
                # 实体已存在，返回现有 UUID
                return result.result_set[0][0]
            
            # 创建新实体 - 将类型信息存储在属性中而不是标签
            # 因为 FalkorDB 标签不支持中文
            safe_type = _sanitize_label(entity_type)
            labels = f"Entity:{safe_type}" if safe_type != "Entity" else "Entity"
            
            create_query = f"""
            CREATE (n:{labels} {{
                uuid: $uuid,
                name: $name,
                entity_type: $entity_type,
                summary: $summary,
                attributes: $attributes,
                created_at: $created_at
            }})
            RETURN n.uuid
            """
            
            self.falkordb.execute_query(graph_id, create_query, {
                "uuid": entity_uuid,
                "name": name,
                "entity_type": entity_type,  # 保留原始类型名
                "summary": summary,
                "attributes": attributes,
                "created_at": datetime.now().isoformat()
            })
            
            logger.debug(f"实体已添加: {name} ({entity_type})")
            return entity_uuid
            
        except Exception as e:
            logger.error(f"添加实体失败: {e}")
            return None
    
    def _add_relation(self, graph_id: str, relation: Dict[str, Any]) -> bool:
        """添加关系到图谱"""
        try:
            source_name = relation.get("source", "")
            target_name = relation.get("target", "")
            relation_type = relation.get("relation_type", "RELATED_TO").upper().replace(" ", "_")
            fact = relation.get("fact", "")
            
            if not source_name or not target_name:
                return False
            
            # 将关系类型转换为有效的 Cypher 标识符
            safe_relation_type = _sanitize_label(relation_type)
            
            # 创建关系（如果节点不存在则同时创建）
            query = f"""
            MERGE (s:Entity {{name: $source_name}})
            ON CREATE SET s.uuid = $source_uuid, s.created_at = $created_at
            MERGE (t:Entity {{name: $target_name}})
            ON CREATE SET t.uuid = $target_uuid, t.created_at = $created_at
            MERGE (s)-[r:{safe_relation_type}]->(t)
            SET r.fact = $fact, r.uuid = $rel_uuid, r.relation_type = $original_type
            RETURN r.uuid
            """
            
            self.falkordb.execute_query(graph_id, query, {
                "source_name": source_name,
                "target_name": target_name,
                "source_uuid": uuid.uuid4().hex,
                "target_uuid": uuid.uuid4().hex,
                "rel_uuid": uuid.uuid4().hex,
                "fact": fact,
                "original_type": relation_type,  # 保留原始关系类型
                "created_at": datetime.now().isoformat()
            })
            
            logger.debug(f"关系已添加: {source_name} --[{relation_type}]--> {target_name}")
            return True
            
        except Exception as e:
            logger.error(f"添加关系失败: {e}")
            return False
    
    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """获取图谱信息"""
        try:
            # 查询节点数量
            node_result = self.falkordb.execute_query(
                graph_id, 
                "MATCH (n:Entity) RETURN count(n) AS count"
            )
            node_count = node_result.result_set[0][0] if node_result.result_set else 0
            
            # 查询边数量
            edge_result = self.falkordb.execute_query(
                graph_id,
                "MATCH ()-[r]->() RETURN count(r) AS count"
            )
            edge_count = edge_result.result_set[0][0] if edge_result.result_set else 0
            
            # 查询实体类型
            labels_result = self.falkordb.execute_query(
                graph_id,
                "MATCH (n) RETURN DISTINCT labels(n) AS labels"
            )
            entity_types = set()
            for row in labels_result.result_set or []:
                for label in row[0]:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)
            
            return GraphInfo(
                graph_id=graph_id,
                node_count=node_count,
                edge_count=edge_count,
                entity_types=list(entity_types)
            )
            
        except Exception as e:
            logger.error(f"获取图谱信息失败: {e}")
            return GraphInfo(graph_id=graph_id, node_count=0, edge_count=0, entity_types=[])
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """获取完整图谱数据"""
        try:
            # 查询所有节点
            nodes_result = self.falkordb.execute_query(
                graph_id,
                """
                MATCH (n:Entity)
                RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels, 
                       n.summary AS summary, n.attributes AS attributes
                """
            )
            
            nodes = []
            for row in nodes_result.result_set or []:
                nodes.append({
                    "uuid": row[0],
                    "name": row[1],
                    "labels": row[2],
                    "summary": row[3] or "",
                    "attributes": json.loads(row[4]) if row[4] else {}
                })
            
            # 查询所有边
            edges_result = self.falkordb.execute_query(
                graph_id,
                """
                MATCH (s:Entity)-[r]->(t:Entity)
                RETURN r.uuid AS uuid, type(r) AS type, r.fact AS fact,
                       s.uuid AS source_uuid, t.uuid AS target_uuid,
                       s.name AS source_name, t.name AS target_name
                """
            )
            
            edges = []
            for row in edges_result.result_set or []:
                edges.append({
                    "uuid": row[0],
                    "name": row[1],  # 前端期望 name 字段作为关系类型
                    "type": row[1],
                    "fact": row[2] or "",
                    "source_node_uuid": row[3],  # 与前端期望的字段名一致
                    "target_node_uuid": row[4],  # 与前端期望的字段名一致
                    "source_name": row[5],
                    "target_name": row[6],
                })
            
            return {
                "graph_id": graph_id,
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "backend": "falkordb",
            }
            
        except Exception as e:
            logger.error(f"获取图谱数据失败: {e}")
            return {
                "graph_id": graph_id,
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "backend": "falkordb",
            }
    
    def delete_graph(self, graph_id: str):
        """删除图谱"""
        try:
            if graph_id in self._graphs:
                del self._graphs[graph_id]
            # FalkorDB 删除所有节点和关系
            self.falkordb.execute_query(graph_id, "MATCH (n) DETACH DELETE n")
            logger.info(f"FalkorDB 图谱已删除: {graph_id}")
        except Exception as e:
            logger.error(f"删除图谱失败: {e}")


class GraphitiEntityReader:
    """
    FalkorDB 版实体读取服务
    提供与 ZepEntityReader 兼容的接口
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """初始化"""
        self._falkordb = None
    
    @property
    def falkordb(self) -> FalkorDBClient:
        """延迟初始化 FalkorDB 客户端"""
        if self._falkordb is None:
            self._falkordb = _get_falkordb_client()
        return self._falkordb
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """获取图谱的所有节点"""
        logger.info(f"获取图谱 {graph_id} 的所有节点...")
        
        try:
            result = self.falkordb.execute_query(
                graph_id,
                """
                MATCH (n:Entity)
                RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
                       n.summary AS summary, n.attributes AS attributes
                """
            )
            
            nodes_data = []
            for row in result.result_set or []:
                nodes_data.append({
                    "uuid": row[0] or "",
                    "name": row[1] or "",
                    "labels": row[2] or [],
                    "summary": row[3] or "",
                    "attributes": json.loads(row[4]) if row[4] else {},
                })
            
            logger.info(f"共获取 {len(nodes_data)} 个节点")
            return nodes_data
            
        except Exception as e:
            logger.error(f"获取节点失败: {e}")
            return []
    
    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """获取图谱的所有边"""
        logger.info(f"获取图谱 {graph_id} 的所有边...")
        
        try:
            result = self.falkordb.execute_query(
                graph_id,
                """
                MATCH (s:Entity)-[r]->(t:Entity)
                RETURN r.uuid AS uuid, type(r) AS name, r.fact AS fact,
                       s.uuid AS source_node_uuid, t.uuid AS target_node_uuid
                """
            )
            
            edges_data = []
            for row in result.result_set or []:
                edges_data.append({
                    "uuid": row[0] or "",
                    "name": row[1] or "",
                    "fact": row[2] or "",
                    "source_node_uuid": row[3],
                    "target_node_uuid": row[4],
                    "attributes": {},
                })
            
            logger.info(f"共获取 {len(edges_data)} 条边")
            return edges_data
            
        except Exception as e:
            logger.error(f"获取边失败: {e}")
            return []
    
    def get_node_edges(self, node_uuid: str) -> List[Any]:
        """获取指定节点的所有相关边"""
        # 需要遍历所有图谱查找，这里简化处理
        return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """筛选出符合预定义实体类型的节点"""
        logger.info(f"开始筛选图谱 {graph_id} 的实体...")
        
        # 获取所有节点
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # 获取所有边
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # 构建节点 UUID 到节点数据的映射
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # 筛选符合条件的实体
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            
            # 筛选逻辑：Labels 必须包含除 "Entity" 和 "Node" 之外的标签
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            if not custom_labels:
                continue
            
            # 如果指定了预定义类型，检查是否匹配
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]
            
            entity_types_found.add(entity_type)
            
            # 创建实体节点对象
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # 获取相关边和节点
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()
                
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                
                entity.related_edges = related_edges
                
                # 获取关联节点的基本信息
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })
                
                entity.related_nodes = related_nodes
            
            filtered_entities.append(entity)
        
        logger.info(f"筛选完成: 总节点 {total_count}, 符合条件 {len(filtered_entities)}, "
                   f"实体类型: {entity_types_found}")
        
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )
    
    def get_entity_with_context(
        self, 
        graph_id: str, 
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """获取单个实体及其完整上下文"""
        try:
            # 查询实体
            result = self.falkordb.execute_query(
                graph_id,
                """
                MATCH (n:Entity {uuid: $uuid})
                RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
                       n.summary AS summary, n.attributes AS attributes
                """,
                {"uuid": entity_uuid}
            )
            
            if not result.result_set:
                return None
            
            row = result.result_set[0]
            entity = EntityNode(
                uuid=row[0],
                name=row[1],
                labels=row[2],
                summary=row[3] or "",
                attributes=json.loads(row[4]) if row[4] else {},
            )
            
            # 查询相关边
            edges_result = self.falkordb.execute_query(
                graph_id,
                """
                MATCH (n:Entity {uuid: $uuid})-[r]-(m:Entity)
                RETURN type(r) AS type, r.fact AS fact, 
                       m.uuid AS other_uuid, m.name AS other_name,
                       CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END AS direction
                """,
                {"uuid": entity_uuid}
            )
            
            related_edges = []
            related_nodes = []
            seen_uuids = set()
            
            for edge_row in edges_result.result_set or []:
                related_edges.append({
                    "edge_name": edge_row[0],
                    "fact": edge_row[1] or "",
                    "other_uuid": edge_row[2],
                    "direction": edge_row[4],
                })
                
                if edge_row[2] not in seen_uuids:
                    seen_uuids.add(edge_row[2])
                    related_nodes.append({
                        "uuid": edge_row[2],
                        "name": edge_row[3],
                    })
            
            entity.related_edges = related_edges
            entity.related_nodes = related_nodes
            
            return entity
            
        except Exception as e:
            logger.error(f"获取实体上下文失败: {e}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """获取指定类型的所有实体"""
        try:
            result = self.falkordb.execute_query(
                graph_id,
                f"""
                MATCH (n:{entity_type})
                RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
                       n.summary AS summary, n.attributes AS attributes
                """
            )
            
            entities = []
            for row in result.result_set or []:
                entity = EntityNode(
                    uuid=row[0],
                    name=row[1],
                    labels=row[2],
                    summary=row[3] or "",
                    attributes=json.loads(row[4]) if row[4] else {},
                )
                entities.append(entity)
            
            return entities
            
        except Exception as e:
            logger.error(f"获取类型实体失败: {e}")
            return []


# 工厂函数：根据配置返回合适的服务实例
def get_graph_builder_service(api_key: Optional[str] = None):
    """
    获取图谱构建服务
    根据 USE_GRAPHITI 配置返回 FalkorDB 或 Zep 实现
    """
    if Config.USE_GRAPHITI:
        logger.info("使用 FalkorDB 自托管图谱服务")
        return GraphitiGraphBuilder(api_key)
    else:
        from .graph_builder import GraphBuilderService
        logger.info("使用 Zep Cloud 图谱服务")
        return GraphBuilderService(api_key)


def get_entity_reader_service(api_key: Optional[str] = None):
    """
    获取实体读取服务
    根据 USE_GRAPHITI 配置返回 FalkorDB 或 Zep 实现
    """
    if Config.USE_GRAPHITI:
        logger.info("使用 FalkorDB 自托管实体读取服务")
        return GraphitiEntityReader(api_key)
    else:
        from .zep_entity_reader import ZepEntityReader
        logger.info("使用 Zep Cloud 实体读取服务")
        return ZepEntityReader(api_key)


# ==================== GraphitiToolsService ====================
# 提供与 ZepToolsService 兼容的接口，使 report_agent 可以使用 FalkorDB


@dataclass
class GraphitiSearchResult:
    """搜索结果（与 zep_tools.SearchResult 兼容）"""
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count
        }
    
    def to_text(self) -> str:
        """转换为文本格式，供LLM理解"""
        text_parts = [f"搜索查询: {self.query}", f"找到 {self.total_count} 条相关信息"]
        
        if self.facts:
            text_parts.append("\n### 相关事实:")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")
        
        return "\n".join(text_parts)


@dataclass
class GraphitiInsightResult:
    """深度洞察结果（与 zep_tools.InsightForgeResult 兼容）"""
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    semantic_facts: List[str] = field(default_factory=list)
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)
    relationship_chains: List[str] = field(default_factory=list)
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships
        }
    
    def to_text(self) -> str:
        """转换为详细的文本格式"""
        text_parts = [
            f"## 深度分析结果",
            f"分析问题: {self.query}",
            f"预测场景: {self.simulation_requirement}",
            f"\n### 数据统计",
            f"- 相关事实: {self.total_facts}条",
            f"- 涉及实体: {self.total_entities}个",
            f"- 关系链: {self.total_relationships}条"
        ]
        
        if self.sub_queries:
            text_parts.append(f"\n### 分析的子问题")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")
        
        if self.semantic_facts:
            text_parts.append(f"\n### 【关键事实】")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f'{i}. "{fact}"')
        
        if self.entity_insights:
            text_parts.append(f"\n### 【核心实体】")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', '未知')}** ({entity.get('type', '实体')})")
                if entity.get('summary'):
                    text_parts.append(f'  摘要: "{entity.get("summary")}"')
        
        if self.relationship_chains:
            text_parts.append(f"\n### 【关系链】")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")
        
        return "\n".join(text_parts)


@dataclass
class GraphitiPanoramaResult:
    """广度搜索结果（与 zep_tools.PanoramaResult 兼容）"""
    query: str
    all_nodes: List[Dict[str, Any]] = field(default_factory=list)
    all_edges: List[Dict[str, Any]] = field(default_factory=list)
    active_facts: List[str] = field(default_factory=list)
    historical_facts: List[str] = field(default_factory=list)
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": self.all_nodes,
            "all_edges": self.all_edges,
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count
        }
    
    def to_text(self) -> str:
        """转换为文本格式"""
        text_parts = [
            f"## 广度搜索结果",
            f"查询: {self.query}",
            f"\n### 统计信息",
            f"- 总节点数: {self.total_nodes}",
            f"- 总边数: {self.total_edges}",
            f"- 当前有效事实: {self.active_count}条"
        ]
        
        if self.active_facts:
            text_parts.append(f"\n### 【当前有效事实】")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f'{i}. "{fact}"')
        
        if self.all_nodes:
            text_parts.append(f"\n### 【涉及实体】")
            for node in self.all_nodes[:20]:  # 限制显示数量
                name = node.get("name", "未知")
                labels = node.get("labels", [])
                entity_type = next((l for l in labels if l not in ["Entity", "Node"]), "实体")
                text_parts.append(f"- **{name}** ({entity_type})")
        
        return "\n".join(text_parts)


@dataclass
class GraphitiInterviewResult:
    """采访结果（与 zep_tools.InterviewResult 兼容）"""
    interview_topic: str
    interview_questions: List[str] = field(default_factory=list)
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    interviews: List[Dict[str, Any]] = field(default_factory=list)
    selection_reasoning: str = ""
    summary: str = ""
    total_agents: int = 0
    interviewed_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "interviews": self.interviews,
            "selection_reasoning": self.selection_reasoning,
            "summary": self.summary,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count
        }
    
    def to_text(self) -> str:
        """转换为文本格式"""
        text_parts = [
            f"## 🎤 Agent采访报告",
            f"**采访主题:** {self.interview_topic}",
            f"**采访人数:** {self.interviewed_count} 位Agent"
        ]
        
        if self.selection_reasoning:
            text_parts.append(f"\n### 采访对象选择理由")
            text_parts.append(self.selection_reasoning)
        
        if self.interviews:
            text_parts.append(f"\n### 采访实录")
            for i, interview in enumerate(self.interviews, 1):
                agent_name = interview.get("agent_name", f"Agent_{i}")
                agent_role = interview.get("agent_role", "未知角色")
                response = interview.get("response", "")
                text_parts.append(f"\n#### {agent_name} ({agent_role})")
                text_parts.append(f"{response}")
        
        if self.summary:
            text_parts.append(f"\n### 采访摘要")
            text_parts.append(self.summary)
        
        return "\n".join(text_parts)


class GraphitiToolsService:
    """
    FalkorDB 检索工具服务
    
    提供与 ZepToolsService 兼容的接口，使 report_agent 可以在 FalkorDB 后端下正常工作。
    """
    
    def __init__(self, api_key: Optional[str] = None, llm_client = None):
        self._falkordb = None
        self._llm_client = llm_client
        logger.info("GraphitiToolsService 初始化完成（使用 FalkorDB）")
    
    @property
    def falkordb(self) -> FalkorDBClient:
        """延迟初始化 FalkorDB 客户端"""
        if self._falkordb is None:
            self._falkordb = _get_falkordb_client()
        return self._falkordb
    
    @property
    def llm(self):
        """延迟初始化 LLM 客户端"""
        if self._llm_client is None:
            from ..utils.llm_client import LLMClient
            self._llm_client = LLMClient()
        return self._llm_client
    
    def _get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """获取图谱的所有节点"""
        try:
            result = self.falkordb.execute_query(
                graph_id,
                """
                MATCH (n:Entity)
                RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
                       n.summary AS summary, n.attributes AS attributes, n.entity_type AS entity_type
                """
            )
            
            nodes = []
            for row in result.result_set or []:
                nodes.append({
                    "uuid": row[0] or "",
                    "name": row[1] or "",
                    "labels": row[2] or [],
                    "summary": row[3] or "",
                    "attributes": json.loads(row[4]) if row[4] else {},
                    "entity_type": row[5] or ""
                })
            return nodes
        except Exception as e:
            logger.error(f"获取节点失败: {e}")
            return []
    
    def _get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """获取图谱的所有边"""
        try:
            result = self.falkordb.execute_query(
                graph_id,
                """
                MATCH (s:Entity)-[r]->(t:Entity)
                RETURN r.uuid AS uuid, type(r) AS name, r.fact AS fact,
                       s.uuid AS source_node_uuid, t.uuid AS target_node_uuid,
                       s.name AS source_name, t.name AS target_name
                """
            )
            
            edges = []
            for row in result.result_set or []:
                edges.append({
                    "uuid": row[0] or "",
                    "name": row[1] or "",
                    "fact": row[2] or "",
                    "source_node_uuid": row[3] or "",
                    "target_node_uuid": row[4] or "",
                    "source_name": row[5] or "",
                    "target_name": row[6] or ""
                })
            return edges
        except Exception as e:
            logger.error(f"获取边失败: {e}")
            return []
    
    def _keyword_search(self, items: List[Dict], query: str, key_fields: List[str], limit: int = 10) -> List[Dict]:
        """简单的关键词搜索"""
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def score(item: Dict) -> int:
            s = 0
            for field in key_fields:
                text = str(item.get(field, "")).lower()
                if query_lower in text:
                    s += 100
                for kw in keywords:
                    if kw in text:
                        s += 10
            return s
        
        scored = [(score(item), item) for item in items]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for s, item in scored[:limit] if s > 0]
    
    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """获取图谱统计信息"""
        try:
            nodes = self._get_all_nodes(graph_id)
            edges = self._get_all_edges(graph_id)
            
            # 统计实体类型
            entity_types = {}
            for node in nodes:
                for label in node.get("labels", []):
                    if label not in ["Entity", "Node"]:
                        entity_types[label] = entity_types.get(label, 0) + 1
            
            return {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "entity_types": entity_types
            }
        except Exception as e:
            logger.error(f"获取图谱统计失败: {e}")
            return {"total_nodes": 0, "total_edges": 0, "entity_types": {}}
    
    def get_simulation_context(
        self, 
        graph_id: str, 
        simulation_requirement: str, 
        limit: int = 20
    ) -> Dict[str, Any]:
        """获取模拟上下文"""
        logger.info(f"获取模拟上下文: {simulation_requirement[:50]}...")
        
        # 获取所有数据
        all_nodes = self._get_all_nodes(graph_id)
        all_edges = self._get_all_edges(graph_id)
        
        # 搜索相关事实
        related_edges = self._keyword_search(all_edges, simulation_requirement, ["fact", "name"], limit)
        facts = [e.get("fact", "") for e in related_edges if e.get("fact")]
        
        # 获取统计信息
        stats = self.get_graph_statistics(graph_id)
        
        # 筛选有类型的实体
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.get("labels", []) if l not in ["Entity", "Node"]]
            if custom_labels:
                entities.append({
                    "name": node.get("name", ""),
                    "type": custom_labels[0],
                    "summary": node.get("summary", "")
                })
        
        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": facts,
            "graph_statistics": stats,
            "entities": entities[:limit],
            "total_entities": len(entities)
        }
    
    def quick_search(self, graph_id: str, query: str, limit: int = 10) -> GraphitiSearchResult:
        """简单搜索"""
        logger.info(f"快速搜索: {query[:30]}...")
        
        all_edges = self._get_all_edges(graph_id)
        all_nodes = self._get_all_nodes(graph_id)
        
        # 搜索边
        matched_edges = self._keyword_search(all_edges, query, ["fact", "name", "source_name", "target_name"], limit)
        facts = [e.get("fact", "") for e in matched_edges if e.get("fact")]
        
        # 搜索节点
        matched_nodes = self._keyword_search(all_nodes, query, ["name", "summary"], limit)
        for node in matched_nodes:
            if node.get("summary"):
                facts.append(f"[{node.get('name')}]: {node.get('summary')}")
        
        return GraphitiSearchResult(
            facts=facts,
            edges=matched_edges,
            nodes=matched_nodes,
            query=query,
            total_count=len(facts)
        )
    
    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5
    ) -> GraphitiInsightResult:
        """深度洞察检索"""
        logger.info(f"深度洞察检索: {query[:50]}...")
        
        result = GraphitiInsightResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )
        
        # 获取所有数据
        all_nodes = self._get_all_nodes(graph_id)
        all_edges = self._get_all_edges(graph_id)
        
        # 使用 LLM 生成子问题（简化版本）
        sub_queries = [query]  # 至少包含原始查询
        result.sub_queries = sub_queries
        
        # 收集所有相关事实
        all_facts = []
        seen_facts = set()
        
        for sub_query in sub_queries:
            matched_edges = self._keyword_search(all_edges, sub_query, ["fact", "name"], 20)
            for edge in matched_edges:
                fact = edge.get("fact", "")
                if fact and fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)
        
        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)
        
        # 收集相关实体
        entity_insights = []
        for node in all_nodes:
            custom_labels = [l for l in node.get("labels", []) if l not in ["Entity", "Node"]]
            if custom_labels:
                entity_type = custom_labels[0]
            else:
                entity_type = node.get("entity_type", "实体")
            
            entity_insights.append({
                "uuid": node.get("uuid", ""),
                "name": node.get("name", ""),
                "type": entity_type,
                "summary": node.get("summary", ""),
                "related_facts": []
            })
        
        result.entity_insights = entity_insights[:30]  # 限制数量
        result.total_entities = len(entity_insights)
        
        # 构建关系链
        relationship_chains = []
        for edge in all_edges[:50]:  # 限制数量
            source = edge.get("source_name", edge.get("source_node_uuid", "")[:8])
            target = edge.get("target_name", edge.get("target_node_uuid", "")[:8])
            relation = edge.get("name", "RELATED")
            chain = f"{source} --[{relation}]--> {target}"
            relationship_chains.append(chain)
        
        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)
        
        logger.info(f"深度洞察完成: {result.total_facts}条事实, {result.total_entities}个实体")
        return result
    
    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True
    ) -> GraphitiPanoramaResult:
        """广度搜索"""
        logger.info(f"广度搜索: {query[:30]}...")
        
        all_nodes = self._get_all_nodes(graph_id)
        all_edges = self._get_all_edges(graph_id)
        
        # 收集所有事实
        active_facts = [e.get("fact", "") for e in all_edges if e.get("fact")]
        
        # 按相关性排序
        if query:
            matched_edges = self._keyword_search(all_edges, query, ["fact", "name"], len(all_edges))
            active_facts = [e.get("fact", "") for e in matched_edges if e.get("fact")]
        
        return GraphitiPanoramaResult(
            query=query,
            all_nodes=all_nodes,
            all_edges=all_edges,
            active_facts=active_facts,
            historical_facts=[],  # FalkorDB 不支持时间维度
            total_nodes=len(all_nodes),
            total_edges=len(all_edges),
            active_count=len(active_facts),
            historical_count=0
        )
    
    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int = 5
    ) -> GraphitiInterviewResult:
        """采访 Agent（简化实现）"""
        logger.info(f"采访 Agent: {interview_requirement[:30]}...")
        
        # 这里简化实现，返回空结果
        # 完整实现需要调用 OASIS 采访 API
        return GraphitiInterviewResult(
            interview_topic=interview_requirement,
            interview_questions=[],
            selected_agents=[],
            interviews=[],
            selection_reasoning="FalkorDB 模式下暂不支持 Agent 采访功能",
            summary="",
            total_agents=0,
            interviewed_count=0
        )
    
    def get_entity_summary(self, graph_id: str, entity_name: str) -> Dict[str, Any]:
        """获取实体摘要"""
        try:
            result = self.falkordb.execute_query(
                graph_id,
                """
                MATCH (n:Entity {name: $name})
                OPTIONAL MATCH (n)-[r]-(m:Entity)
                RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
                       n.summary AS summary, collect(DISTINCT {type: type(r), other: m.name}) AS relations
                """,
                {"name": entity_name}
            )
            
            if not result.result_set:
                return {"error": f"未找到实体: {entity_name}"}
            
            row = result.result_set[0]
            return {
                "uuid": row[0],
                "name": row[1],
                "labels": row[2],
                "summary": row[3],
                "relations": row[4] or []
            }
        except Exception as e:
            logger.error(f"获取实体摘要失败: {e}")
            return {"error": str(e)}
    
    def get_entities_by_type(self, graph_id: str, entity_type: str) -> List[Dict[str, Any]]:
        """按类型获取实体"""
        try:
            # 使用 _sanitize_label 转换后的类型查询
            safe_type = _sanitize_label(entity_type)
            
            result = self.falkordb.execute_query(
                graph_id,
                f"""
                MATCH (n:{safe_type})
                RETURN n.uuid AS uuid, n.name AS name, labels(n) AS labels,
                       n.summary AS summary
                """
            )
            
            entities = []
            for row in result.result_set or []:
                entities.append({
                    "uuid": row[0],
                    "name": row[1],
                    "labels": row[2],
                    "summary": row[3] or ""
                })
            
            return entities
        except Exception as e:
            logger.error(f"获取类型实体失败: {e}")
            return []


def get_tools_service(api_key: Optional[str] = None):
    """
    获取检索工具服务
    根据 USE_GRAPHITI 配置返回 FalkorDB 或 Zep 实现
    """
    if Config.USE_GRAPHITI:
        logger.info("使用 FalkorDB 自托管检索工具服务")
        return GraphitiToolsService(api_key)
    else:
        from .zep_tools import ZepToolsService
        logger.info("使用 Zep Cloud 检索工具服务")
        return ZepToolsService(api_key)
