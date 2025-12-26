"""
API 认证工具模块
"""

import os
from functools import wraps
from flask import request, jsonify

from .logger import get_logger

logger = get_logger('mirofish.auth')


def require_api_key(f):
    """
    API Key 认证装饰器
    
    验证请求头中的 X-API-Key 或 URL 参数 api_key
    如果未配置 MIROFISH_API_KEY 环境变量，则跳过验证
    
    Usage:
        @simulation_bp.route('/create', methods=['POST'])
        @require_api_key
        def create_simulation():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        expected_key = os.environ.get('MIROFISH_API_KEY')
        
        # 未配置 API Key，跳过验证（向后兼容）
        if not expected_key:
            return f(*args, **kwargs)
        
        # 从请求头或 URL 参数获取 API Key
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            logger.warning(f"API 请求缺少认证: {request.method} {request.path} from {request.remote_addr}")
            return jsonify({
                "success": False,
                "error": "缺少 API Key，请在请求头中添加 X-API-Key"
            }), 401
        
        if api_key != expected_key:
            logger.warning(f"API Key 验证失败: {request.method} {request.path} from {request.remote_addr}")
            return jsonify({
                "success": False,
                "error": "无效的 API Key"
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function
