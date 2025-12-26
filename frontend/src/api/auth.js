/**
 * 用户认证 API
 */

import api from './index'

/**
 * 用户登录
 * @param {string} username 用户名
 * @param {string} password 密码
 */
export const login = async (username, password) => {
    try {
        const res = await api.post('/api/auth/login', { username, password })
        return res.data
    } catch (error) {
        if (error.response?.data) {
            return error.response.data
        }
        return { success: false, error: error.message }
    }
}

/**
 * 获取当前用户信息
 */
export const getUser = async () => {
    try {
        const token = localStorage.getItem('mirofish_token')
        const res = await api.get('/api/auth/user', {
            headers: { 'X-Auth-Token': token }
        })
        return res.data
    } catch (error) {
        if (error.response?.data) {
            return error.response.data
        }
        return { success: false, error: error.message }
    }
}

/**
 * 修改密码
 * @param {string} oldPassword 旧密码
 * @param {string} newPassword 新密码
 */
export const changePassword = async (oldPassword, newPassword) => {
    try {
        const token = localStorage.getItem('mirofish_token')
        const res = await api.put('/api/auth/password', {
            old_password: oldPassword,
            new_password: newPassword
        }, {
            headers: { 'X-Auth-Token': token }
        })
        return res.data
    } catch (error) {
        if (error.response?.data) {
            return error.response.data
        }
        return { success: false, error: error.message }
    }
}

/**
 * 修改用户名
 * @param {string} newUsername 新用户名
 * @param {string} password 当前密码
 */
export const changeUsername = async (newUsername, password) => {
    try {
        const token = localStorage.getItem('mirofish_token')
        const res = await api.put('/api/auth/username', {
            new_username: newUsername,
            password: password
        }, {
            headers: { 'X-Auth-Token': token }
        })
        return res.data
    } catch (error) {
        if (error.response?.data) {
            return error.response.data
        }
        return { success: false, error: error.message }
    }
}

/**
 * 退出登录
 */
export const logout = () => {
    localStorage.removeItem('mirofish_auth')
    localStorage.removeItem('mirofish_user')
    localStorage.removeItem('mirofish_token')
}
