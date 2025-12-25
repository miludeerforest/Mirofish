<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1 class="logo">MIROFISH</h1>
        <p class="tagline">群体智能引擎 · 预测万物</p>
      </div>
      
      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="username"
            type="text"
            placeholder="请输入用户名"
            autocomplete="username"
            required
          />
        </div>
        
        <div class="form-group">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            required
          />
        </div>
        
        <div v-if="error" class="error-message">
          {{ error }}
        </div>
        
        <button type="submit" class="login-btn" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

// 默认演示账户 (可在部署时通过环境变量覆盖)
const VALID_USERNAME = import.meta.env.VITE_DEMO_USERNAME || 'demo'
const VALID_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD || 'demo123'

const handleLogin = () => {
  error.value = ''
  loading.value = true
  
  // 模拟网络延迟
  setTimeout(() => {
    if (username.value === VALID_USERNAME && password.value === VALID_PASSWORD) {
      // 登录成功，保存认证状态
      localStorage.setItem('mirofish_auth', 'true')
      localStorage.setItem('mirofish_user', username.value)
      router.push('/')
    } else {
      error.value = '用户名或密码错误'
    }
    loading.value = false
  }, 500)
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  padding: 20px;
}

.login-card {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  padding: 48px 40px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.login-header {
  text-align: center;
  margin-bottom: 40px;
}

.logo {
  font-size: 32px;
  font-weight: 800;
  color: #1a1a2e;
  letter-spacing: 4px;
  margin-bottom: 8px;
}

.tagline {
  color: #666;
  font-size: 14px;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.form-group input {
  padding: 14px 16px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 16px;
  transition: all 0.3s ease;
  outline: none;
}

.form-group input:focus {
  border-color: #1a1a2e;
  box-shadow: 0 0 0 3px rgba(26, 26, 46, 0.1);
}

.form-group input::placeholder {
  color: #aaa;
}

.error-message {
  background: #fff5f5;
  color: #e53e3e;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 14px;
  border: 1px solid #feb2b2;
}

.login-btn {
  padding: 16px;
  background: #1a1a2e;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
}

.login-btn:hover:not(:disabled) {
  background: #16213e;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(26, 26, 46, 0.3);
}

.login-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
</style>
