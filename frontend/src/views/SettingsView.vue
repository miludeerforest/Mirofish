<template>
  <div class="settings-container">
    <div class="settings-card">
      <div class="settings-header">
        <h1>账号设置</h1>
        <button class="btn-logout" @click="handleLogout">退出登录</button>
      </div>

      <!-- 当前用户信息 -->
      <div class="info-section">
        <h2>当前账号</h2>
        <div class="info-item">
          <span class="label">用户名:</span>
          <span class="value">{{ currentUser }}</span>
        </div>
      </div>

      <!-- 修改用户名 -->
      <div class="form-section">
        <h2>修改用户名</h2>
        <form @submit.prevent="handleChangeUsername">
          <div class="form-group">
            <label>新用户名</label>
            <input
              v-model="newUsername"
              type="text"
              placeholder="至少3个字符"
              minlength="3"
              required
            />
          </div>
          <div class="form-group">
            <label>当前密码（验证身份）</label>
            <input
              v-model="usernamePassword"
              type="password"
              placeholder="请输入当前密码"
              required
            />
          </div>
          <div v-if="usernameMessage" :class="['message', usernameSuccess ? 'success' : 'error']">
            {{ usernameMessage }}
          </div>
          <button type="submit" class="btn-submit" :disabled="usernameLoading">
            {{ usernameLoading ? '修改中...' : '修改用户名' }}
          </button>
        </form>
      </div>

      <!-- 修改密码 -->
      <div class="form-section">
        <h2>修改密码</h2>
        <form @submit.prevent="handleChangePassword">
          <div class="form-group">
            <label>当前密码</label>
            <input
              v-model="oldPassword"
              type="password"
              placeholder="请输入当前密码"
              required
            />
          </div>
          <div class="form-group">
            <label>新密码</label>
            <input
              v-model="newPassword"
              type="password"
              placeholder="至少6个字符"
              minlength="6"
              required
            />
          </div>
          <div class="form-group">
            <label>确认新密码</label>
            <input
              v-model="confirmPassword"
              type="password"
              placeholder="再次输入新密码"
              required
            />
          </div>
          <div v-if="passwordMessage" :class="['message', passwordSuccess ? 'success' : 'error']">
            {{ passwordMessage }}
          </div>
          <button type="submit" class="btn-submit" :disabled="passwordLoading">
            {{ passwordLoading ? '修改中...' : '修改密码' }}
          </button>
        </form>
      </div>

      <!-- 返回首页 -->
      <div class="actions">
        <router-link to="/" class="btn-back">← 返回首页</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { changePassword, changeUsername, logout } from '../api/auth'

const router = useRouter()

// 当前用户
const currentUser = ref(localStorage.getItem('mirofish_user') || 'admin')

// 修改用户名表单
const newUsername = ref('')
const usernamePassword = ref('')
const usernameLoading = ref(false)
const usernameMessage = ref('')
const usernameSuccess = ref(false)

// 修改密码表单
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const passwordLoading = ref(false)
const passwordMessage = ref('')
const passwordSuccess = ref(false)

const handleChangeUsername = async () => {
  usernameMessage.value = ''
  
  if (newUsername.value.length < 3) {
    usernameMessage.value = '用户名至少3个字符'
    usernameSuccess.value = false
    return
  }
  
  usernameLoading.value = true
  
  const res = await changeUsername(newUsername.value, usernamePassword.value)
  
  if (res.success) {
    usernameSuccess.value = true
    usernameMessage.value = '用户名修改成功'
    currentUser.value = newUsername.value
    localStorage.setItem('mirofish_user', newUsername.value)
    if (res.data?.token) {
      localStorage.setItem('mirofish_token', res.data.token)
    }
    newUsername.value = ''
    usernamePassword.value = ''
  } else {
    usernameSuccess.value = false
    usernameMessage.value = res.error || '修改失败'
  }
  
  usernameLoading.value = false
}

const handleChangePassword = async () => {
  passwordMessage.value = ''
  
  if (newPassword.value !== confirmPassword.value) {
    passwordMessage.value = '两次输入的密码不一致'
    passwordSuccess.value = false
    return
  }
  
  if (newPassword.value.length < 6) {
    passwordMessage.value = '新密码至少6个字符'
    passwordSuccess.value = false
    return
  }
  
  passwordLoading.value = true
  
  const res = await changePassword(oldPassword.value, newPassword.value)
  
  if (res.success) {
    passwordSuccess.value = true
    passwordMessage.value = '密码修改成功'
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } else {
    passwordSuccess.value = false
    passwordMessage.value = res.error || '修改失败'
  }
  
  passwordLoading.value = false
}

const handleLogout = () => {
  logout()
  router.push('/login')
}
</script>

<style scoped>
.settings-container {
  min-height: 100vh;
  background: #f5f7fa;
  padding: 40px 20px;
}

.settings-card {
  max-width: 600px;
  margin: 0 auto;
  background: white;
  border-radius: 16px;
  padding: 40px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding-bottom: 20px;
  border-bottom: 1px solid #eee;
}

.settings-header h1 {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0;
}

.btn-logout {
  background: #f5f5f5;
  color: #666;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-logout:hover {
  background: #e53e3e;
  color: white;
}

.info-section, .form-section {
  margin-bottom: 32px;
}

.info-section h2, .form-section h2 {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 16px;
}

.info-item {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background: #f8f9fa;
  border-radius: 8px;
}

.info-item .label {
  color: #666;
}

.info-item .value {
  color: #1a1a2e;
  font-weight: 600;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #333;
  margin-bottom: 6px;
}

.form-group input {
  width: 100%;
  padding: 12px 14px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 14px;
  transition: all 0.2s;
  box-sizing: border-box;
}

.form-group input:focus {
  outline: none;
  border-color: #1a1a2e;
}

.message {
  padding: 12px;
  border-radius: 6px;
  font-size: 14px;
  margin-bottom: 16px;
}

.message.success {
  background: #f0fff4;
  color: #38a169;
  border: 1px solid #9ae6b4;
}

.message.error {
  background: #fff5f5;
  color: #e53e3e;
  border: 1px solid #feb2b2;
}

.btn-submit {
  width: 100%;
  padding: 14px;
  background: #1a1a2e;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-submit:hover:not(:disabled) {
  background: #16213e;
}

.btn-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.actions {
  margin-top: 32px;
  padding-top: 20px;
  border-top: 1px solid #eee;
}

.btn-back {
  color: #666;
  text-decoration: none;
  font-size: 14px;
  transition: color 0.2s;
}

.btn-back:hover {
  color: #1a1a2e;
}
</style>
