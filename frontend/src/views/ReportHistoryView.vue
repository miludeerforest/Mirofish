<template>
  <div class="history-container">
    <!-- 顶部导航栏 -->
    <nav class="navbar">
      <div class="nav-brand" @click="router.push('/')">MIROFISH</div>
      <div class="nav-title">历史报告</div>
      <div class="nav-actions">
        <button class="back-btn" @click="router.push('/')">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
          返回首页
        </button>
      </div>
    </nav>

    <!-- 主内容区 -->
    <main class="main-content">
      <div class="content-header">
        <h1 class="page-title">模拟报告历史</h1>
        <p class="page-desc">查看和管理所有已生成的预测报告</p>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <div class="loading-spinner"></div>
        <span>加载中...</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="reports.length === 0" class="empty-state">
        <div class="empty-icon">📊</div>
        <h3>暂无报告</h3>
        <p>完成一次模拟后，报告将显示在这里</p>
        <button class="start-btn" @click="router.push('/')">开始新模拟</button>
      </div>

      <!-- 报告列表 -->
      <div v-else class="reports-grid">
        <div 
          v-for="report in reports" 
          :key="report.report_id" 
          class="report-card"
          :class="{ 'is-completed': report.status === 'completed' }"
        >
          <div class="card-header">
            <span class="report-id">{{ report.report_id }}</span>
            <span class="status-badge" :class="report.status">
              {{ getStatusText(report.status) }}
            </span>
          </div>
          
          <h3 class="report-title">{{ report.outline?.title || '未命名报告' }}</h3>
          <p class="report-summary">{{ report.outline?.summary || '暂无摘要' }}</p>
          
          <div class="card-meta">
            <span class="meta-item">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="16" y1="2" x2="16" y2="6"></line>
                <line x1="8" y1="2" x2="8" y2="6"></line>
                <line x1="3" y1="10" x2="21" y2="10"></line>
              </svg>
              {{ formatDate(report.created_at) }}
            </span>
            <span class="meta-item">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
              </svg>
              {{ report.outline?.sections?.length || 0 }} 章节
            </span>
          </div>
          
          <div class="card-actions">
            <button class="action-btn view" @click="viewReport(report.report_id)">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
              </svg>
              查看
            </button>
            <button class="action-btn download" @click="handleDownload(report.report_id)" :disabled="report.status !== 'completed'">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
              下载
            </button>
            <button class="action-btn delete" @click="handleDelete(report.report_id)">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
              删除
            </button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listReports, downloadReport, deleteReport } from '../api/report'

const router = useRouter()

const reports = ref([])
const loading = ref(true)

const loadReports = async () => {
  loading.value = true
  try {
    const res = await listReports({ limit: 50 })
    if (res.success && res.data) {
      reports.value = res.data
    }
  } catch (err) {
    console.error('加载报告列表失败:', err)
  } finally {
    loading.value = false
  }
}

const getStatusText = (status) => {
  const map = {
    'completed': '已完成',
    'generating': '生成中',
    'failed': '失败',
    'pending': '待处理'
  }
  return map[status] || status
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  try {
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return dateStr
  }
}

const viewReport = (reportId) => {
  router.push({ name: 'Report', params: { reportId } })
}

const handleDownload = (reportId) => {
  downloadReport(reportId)
}

const handleDelete = async (reportId) => {
  if (!confirm('确定要删除这个报告吗？此操作不可撤销。')) return
  
  try {
    const res = await deleteReport(reportId)
    if (res.success) {
      reports.value = reports.value.filter(r => r.report_id !== reportId)
    } else {
      alert('删除失败: ' + (res.error || '未知错误'))
    }
  } catch (err) {
    alert('删除失败: ' + err.message)
  }
}

onMounted(() => {
  loadReports()
})
</script>

<style scoped>
.history-container {
  min-height: 100vh;
  background: #F8F9FA;
  font-family: 'Space Grotesk', -apple-system, sans-serif;
}

/* 导航栏 */
.navbar {
  height: 60px;
  background: #000;
  color: #FFF;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 40px;
}

.nav-brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  letter-spacing: 1px;
  cursor: pointer;
}

.nav-title {
  font-weight: 600;
  font-size: 14px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.3);
  color: #FFF;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.5);
}

/* 主内容 */
.main-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px;
}

.content-header {
  margin-bottom: 40px;
}

.page-title {
  font-size: 2rem;
  font-weight: 700;
  margin: 0 0 8px 0;
}

.page-desc {
  color: #666;
  margin: 0;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px;
  color: #666;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #E5E7EB;
  border-top-color: #000;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 80px;
  background: #FFF;
  border-radius: 8px;
  border: 1px solid #E5E7EB;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state h3 {
  margin: 0 0 8px 0;
  font-size: 1.25rem;
}

.empty-state p {
  color: #666;
  margin: 0 0 24px 0;
}

.start-btn {
  padding: 12px 24px;
  background: #000;
  color: #FFF;
  border: none;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.start-btn:hover {
  background: #333;
}

/* 报告网格 */
.reports-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 24px;
}

.report-card {
  background: #FFF;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 24px;
  transition: all 0.2s;
}

.report-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  transform: translateY(-2px);
}

.report-card.is-completed {
  border-left: 3px solid #10B981;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.report-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #999;
}

.status-badge {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  text-transform: uppercase;
}

.status-badge.completed {
  background: #D1FAE5;
  color: #059669;
}

.status-badge.generating {
  background: #FEF3C7;
  color: #D97706;
}

.status-badge.failed {
  background: #FEE2E2;
  color: #DC2626;
}

.report-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 8px 0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.report-summary {
  font-size: 13px;
  color: #666;
  margin: 0 0 16px 0;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #F3F4F6;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #999;
}

.meta-item svg {
  opacity: 0.6;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid #E5E7EB;
  background: #FFF;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: #F9FAFB;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.view {
  color: #3B82F6;
  border-color: #BFDBFE;
}

.action-btn.view:hover {
  background: #EFF6FF;
}

.action-btn.download {
  color: #10B981;
  border-color: #A7F3D0;
}

.action-btn.download:hover:not(:disabled) {
  background: #ECFDF5;
}

.action-btn.delete {
  color: #EF4444;
  border-color: #FECACA;
}

.action-btn.delete:hover {
  background: #FEF2F2;
}
</style>
