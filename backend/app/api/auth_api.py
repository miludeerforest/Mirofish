"""
用户认证API
支持登录验证和密码修改
"""

import os
import json
import hashlib
import secrets
from functools import wraps
from flask import Blueprint, request, jsonify, session

from ..utils.logger import get_logger

logger = get_logger('mirofish.auth_api')

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# 凭证文件路径
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), '../../.credentials.json')

# 默认账号密码
DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = 'admin123'


def _hash_password(password: str, salt: str = None) -> tuple:
    """哈希密码"""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return salt, hashed.hex()


def _load_credentials() -> dict:
    """加载凭证"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载凭证失败: {e}")
    
    # 返回默认凭证
    salt, hashed = _hash_password(DEFAULT_PASSWORD)
    return {
        'username': DEFAULT_USERNAME,
        'password_hash': hashed,
        'salt': salt
    }


def _save_credentials(credentials: dict):
    """保存凭证"""
    try:
        with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(credentials, f, ensure_ascii=False, indent=2)
        logger.info("凭证已保存")
    except Exception as e:
        logger.error(f"保存凭证失败: {e}")
        raise


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """验证密码"""
    _, hashed = _hash_password(password, salt)
    return hashed == stored_hash


def require_login(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查 session 或 header token
        auth_token = request.headers.get('X-Auth-Token') or request.cookies.get('auth_token')
        
        if not auth_token:
            return jsonify({
                "success": False,
                "error": "未登录"
            }), 401
        
        # 验证 token（简单实现：token = username 的 hash）
        credentials = _load_credentials()
        expected_token = hashlib.sha256(credentials['username'].encode()).hexdigest()[:32]
        
        if auth_token != expected_token:
            return jsonify({
                "success": False,
                "error": "登录已过期"
            }), 401
        
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    登录验证
    
    请求:
        {
            "username": "admin",
            "password": "admin123"
        }
    
    返回:
        {
            "success": true,
            "data": {
                "username": "admin",
                "token": "xxxx"
            }
        }
    """
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({
                "success": False,
                "error": "请输入用户名和密码"
            }), 400
        
        credentials = _load_credentials()
        
        # 验证用户名
        if username != credentials['username']:
            logger.warning(f"登录失败：用户名错误 - {username}")
            return jsonify({
                "success": False,
                "error": "用户名或密码错误"
            }), 401
        
        # 验证密码
        if not _verify_password(password, credentials['password_hash'], credentials['salt']):
            logger.warning(f"登录失败：密码错误 - {username}")
            return jsonify({
                "success": False,
                "error": "用户名或密码错误"
            }), 401
        
        # 生成 token
        token = hashlib.sha256(username.encode()).hexdigest()[:32]
        
        logger.info(f"用户登录成功: {username}")
        
        return jsonify({
            "success": True,
            "data": {
                "username": username,
                "token": token
            }
        })
        
    except Exception as e:
        logger.error(f"登录失败: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@auth_bp.route('/user', methods=['GET'])
@require_login
def get_user():
    """获取当前用户信息"""
    credentials = _load_credentials()
    return jsonify({
        "success": True,
        "data": {
            "username": credentials['username']
        }
    })


@auth_bp.route('/password', methods=['PUT'])
@require_login
def change_password():
    """
    修改密码
    
    请求:
        {
            "old_password": "旧密码",
            "new_password": "新密码"
        }
    """
    try:
        data = request.get_json() or {}
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        
        if not old_password or not new_password:
            return jsonify({
                "success": False,
                "error": "请输入旧密码和新密码"
            }), 400
        
        if len(new_password) < 6:
            return jsonify({
                "success": False,
                "error": "新密码至少6个字符"
            }), 400
        
        credentials = _load_credentials()
        
        # 验证旧密码
        if not _verify_password(old_password, credentials['password_hash'], credentials['salt']):
            return jsonify({
                "success": False,
                "error": "旧密码错误"
            }), 400
        
        # 更新密码
        salt, hashed = _hash_password(new_password)
        credentials['password_hash'] = hashed
        credentials['salt'] = salt
        
        _save_credentials(credentials)
        
        logger.info(f"用户 {credentials['username']} 修改了密码")
        
        return jsonify({
            "success": True,
            "message": "密码修改成功"
        })
        
    except Exception as e:
        logger.error(f"修改密码失败: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@auth_bp.route('/username', methods=['PUT'])
@require_login
def change_username():
    """
    修改用户名
    
    请求:
        {
            "new_username": "新用户名",
            "password": "当前密码"
        }
    """
    try:
        data = request.get_json() or {}
        new_username = data.get('new_username', '').strip()
        password = data.get('password', '')
        
        if not new_username or not password:
            return jsonify({
                "success": False,
                "error": "请输入新用户名和当前密码"
            }), 400
        
        if len(new_username) < 3:
            return jsonify({
                "success": False,
                "error": "用户名至少3个字符"
            }), 400
        
        credentials = _load_credentials()
        
        # 验证密码
        if not _verify_password(password, credentials['password_hash'], credentials['salt']):
            return jsonify({
                "success": False,
                "error": "密码错误"
            }), 400
        
        old_username = credentials['username']
        credentials['username'] = new_username
        
        _save_credentials(credentials)
        
        # 生成新 token
        token = hashlib.sha256(new_username.encode()).hexdigest()[:32]
        
        logger.info(f"用户名已修改: {old_username} -> {new_username}")
        
        return jsonify({
            "success": True,
            "data": {
                "username": new_username,
                "token": token
            },
            "message": "用户名修改成功"
        })
        
    except Exception as e:
        logger.error(f"修改用户名失败: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
