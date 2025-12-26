"""
内存监控模块
用于监控和管理模拟进程的内存使用
"""

import gc
import os
import logging
from typing import Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = logging.getLogger(__name__)


class MemoryMonitor:
    """
    内存监控器
    
    功能：
    1. 监控当前进程内存使用
    2. 超过阈值自动执行垃圾回收
    3. 提供内存使用统计
    """
    
    def __init__(self, threshold_percent: float = 80.0, gc_interval: int = 50):
        """
        初始化内存监控器
        
        Args:
            threshold_percent: 内存使用率阈值（百分比），超过时触发 GC
            gc_interval: 强制 GC 间隔（轮数）
        """
        self.threshold_percent = threshold_percent
        self.gc_interval = gc_interval
        self.round_counter = 0
        self.gc_count = 0
        self.last_memory_mb = 0.0
        
    def check_and_cleanup(self, force: bool = False) -> bool:
        """
        检查内存使用并在必要时执行清理
        
        Args:
            force: 是否强制执行 GC
            
        Returns:
            True 如果执行了 GC，False 否则
        """
        self.round_counter += 1
        should_gc = force
        
        # 检查是否达到定期 GC 间隔
        if self.round_counter >= self.gc_interval:
            should_gc = True
            self.round_counter = 0
        
        # 检查内存使用率
        if not should_gc and PSUTIL_AVAILABLE:
            try:
                mem = psutil.virtual_memory()
                if mem.percent > self.threshold_percent:
                    should_gc = True
                    logger.warning(
                        f"内存使用率 {mem.percent:.1f}% 超过阈值 {self.threshold_percent}%，触发 GC"
                    )
            except Exception as e:
                logger.debug(f"获取内存信息失败: {e}")
        
        if should_gc:
            self._do_gc()
            return True
        
        return False
    
    def _do_gc(self):
        """执行垃圾回收"""
        before_mb = self.get_process_memory_mb()
        
        # 执行完整的垃圾回收（所有代）
        gc.collect(0)  # 年轻代
        gc.collect(1)  # 中年代
        gc.collect(2)  # 老年代
        
        after_mb = self.get_process_memory_mb()
        freed_mb = before_mb - after_mb
        
        self.gc_count += 1
        self.last_memory_mb = after_mb
        
        if freed_mb > 1:  # 只记录释放超过 1MB 的情况
            logger.info(f"GC #{self.gc_count}: 释放 {freed_mb:.1f}MB (当前: {after_mb:.1f}MB)")
    
    def get_process_memory_mb(self) -> float:
        """
        获取当前进程内存使用（MB）
        
        Returns:
            内存使用量（MB），如果无法获取返回 0
        """
        if not PSUTIL_AVAILABLE:
            return 0.0
        
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0
    
    def get_system_memory_info(self) -> dict:
        """
        获取系统内存信息
        
        Returns:
            包含系统内存信息的字典
        """
        if not PSUTIL_AVAILABLE:
            return {"available": False}
        
        try:
            mem = psutil.virtual_memory()
            return {
                "available": True,
                "total_mb": mem.total / 1024 / 1024,
                "used_mb": mem.used / 1024 / 1024,
                "free_mb": mem.available / 1024 / 1024,
                "percent": mem.percent
            }
        except Exception:
            return {"available": False}
    
    def get_stats(self) -> dict:
        """
        获取监控统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "gc_count": self.gc_count,
            "round_counter": self.round_counter,
            "last_memory_mb": self.last_memory_mb,
            "process_memory_mb": self.get_process_memory_mb(),
            "system_memory": self.get_system_memory_info()
        }


# 全局单例
_monitor: Optional[MemoryMonitor] = None


def get_memory_monitor(
    threshold_percent: float = 80.0, 
    gc_interval: int = 50
) -> MemoryMonitor:
    """
    获取全局内存监控器实例
    
    Args:
        threshold_percent: 内存阈值（仅首次调用时生效）
        gc_interval: GC 间隔（仅首次调用时生效）
        
    Returns:
        MemoryMonitor 实例
    """
    global _monitor
    if _monitor is None:
        _monitor = MemoryMonitor(threshold_percent, gc_interval)
    return _monitor


def cleanup_model_cache(model) -> bool:
    """
    清理 LLM 模型缓存
    
    尝试清理 camel-ai 或其他 LLM 框架的内部缓存
    
    Args:
        model: LLM 模型对象
        
    Returns:
        True 如果成功清理，False 否则
    """
    cleaned = False
    
    try:
        # 尝试清理 camel-ai 的缓存
        if hasattr(model, '_cache'):
            model._cache.clear()
            cleaned = True
        
        if hasattr(model, 'message_cache'):
            model.message_cache.clear()
            cleaned = True
            
        if hasattr(model, 'history'):
            if hasattr(model.history, 'clear'):
                model.history.clear()
                cleaned = True
            elif isinstance(model.history, list):
                model.history.clear()
                cleaned = True
                
    except Exception as e:
        logger.debug(f"清理模型缓存失败: {e}")
    
    return cleaned
