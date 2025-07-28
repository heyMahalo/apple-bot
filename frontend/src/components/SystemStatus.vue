<template>
  <div class="system-status">
    <h3>系统状态</h3>
    
    <!-- 总览统计 -->
    <el-row :gutter="20" class="status-cards">
      <el-col :span="6">
        <el-card class="status-card">
          <div class="stat-item">
            <div class="stat-icon total">
              <el-icon><DataLine /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-number">{{ systemStatus.total_tasks || 0 }}</div>
              <div class="stat-label">总任务数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="status-card">
          <div class="stat-item">
            <div class="stat-icon active">
              <el-icon><VideoPlay /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-number">{{ systemStatus.active_tasks || 0 }}</div>
              <div class="stat-label">活跃任务</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="status-card">
          <div class="stat-item">
            <div class="stat-icon concurrent">
              <el-icon><Grid /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-number">{{ systemStatus.max_concurrent || 3 }}</div>
              <div class="stat-label">最大并发</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="status-card">
          <div class="stat-item">
            <div class="stat-icon connection" :class="{ connected: isConnected }">
              <el-icon><Connection /></el-icon>
            </div>
            <div class="stat-content">
              <div class="stat-number">{{ isConnected ? '已连接' : '断开' }}</div>
              <div class="stat-label">WebSocket状态</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 系统信息 -->
    <el-card class="info-card">
      <template #header>
        <div class="card-header">
          <span>系统信息</span>
          <el-button 
            size="small" 
            @click="refreshSystemStatus"
            :icon="Refresh"
          >
            刷新
          </el-button>
        </div>
      </template>
      
      <el-descriptions :column="2" border>
        <el-descriptions-item label="系统版本">
          v1.0.0
        </el-descriptions-item>
        <el-descriptions-item label="运行时间">
          {{ uptime }}
        </el-descriptions-item>
        <el-descriptions-item label="WebSocket连接">
          <el-tag :type="isConnected ? 'success' : 'danger'">
            {{ isConnected ? '已连接' : '未连接' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="当前IP">
          {{ currentIP }}
        </el-descriptions-item>
        <el-descriptions-item label="代理轮换">
          <el-tag :type="proxyRotationEnabled ? 'success' : 'info'">
            {{ proxyRotationEnabled ? '已启用' : '未启用' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="最后更新">
          {{ lastUpdateTime }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- IP信息和代理控制 -->
    <el-card class="info-card">
      <template #header>
        <div class="card-header">
          <span>IP和代理设置</span>
          <el-button 
            v-if="proxyRotationEnabled"
            type="primary" 
            size="small"
            @click="rotateIP"
            :loading="rotating"
            :icon="RefreshRight"
          >
            手动切换IP
          </el-button>
        </div>
      </template>
      
      <div class="ip-info">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="当前IP地址">
            <span class="ip-address">{{ ipInfo.ip || ipInfo.proxy_host || '获取中...' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="地理位置">
            {{ ipInfo.country || '未知' }}
          </el-descriptions-item>
          <el-descriptions-item label="使用代理">
            <el-tag :type="ipInfo.using_proxy ? 'success' : 'info'">
              {{ ipInfo.using_proxy ? '是' : '否' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="ipInfo.using_proxy && ipInfo.proxy_port" label="代理端口">
            {{ ipInfo.proxy_port }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <!-- 任务统计图表 -->
    <el-card class="info-card">
      <template #header>
        <span>任务状态分布</span>
      </template>
      
      <div class="task-distribution">
        <div class="distribution-item">
          <div class="distribution-label">等待中</div>
          <el-progress 
            :percentage="getTaskPercentage('pending')"
            :color="'#909399'"
            :show-text="false"
          />
          <span class="distribution-count">{{ getTaskCount('pending') }}</span>
        </div>
        
        <div class="distribution-item">
          <div class="distribution-label">运行中</div>
          <el-progress 
            :percentage="getTaskPercentage('running')"
            :color="'#e6a23c'"
            :show-text="false"
          />
          <span class="distribution-count">{{ getTaskCount('running') }}</span>
        </div>
        
        <div class="distribution-item">
          <div class="distribution-label">已完成</div>
          <el-progress 
            :percentage="getTaskPercentage('completed')"
            :color="'#67c23a'"
            :show-text="false"
          />
          <span class="distribution-count">{{ getTaskCount('completed') }}</span>
        </div>
        
        <div class="distribution-item">
          <div class="distribution-label">失败</div>
          <el-progress 
            :percentage="getTaskPercentage('failed')"
            :color="'#f56c6c'"
            :show-text="false"
          />
          <span class="distribution-count">{{ getTaskCount('failed') }}</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useStore } from 'vuex'
import { ElMessage } from 'element-plus'
import { 
  DataLine, 
  VideoPlay, 
  Grid, 
  Connection, 
  Refresh, 
  RefreshRight 
} from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import axios from 'axios'

import websocketService from '../services/websocket.js'

export default {
  name: 'SystemStatus',
  setup() {
    const store = useStore()
    const rotating = ref(false)
    const startTime = ref(dayjs())
    const currentTime = ref(dayjs())
    const timer = ref(null)

    // 计算属性
    const isConnected = computed(() => store.getters.isConnected)
    const systemStatus = computed(() => store.getters.getSystemStatus)
    const allTasks = computed(() => store.getters.getTasks)

    const uptime = computed(() => {
      const duration = currentTime.value.diff(startTime.value, 'second')
      const hours = Math.floor(duration / 3600)
      const minutes = Math.floor((duration % 3600) / 60)
      const seconds = duration % 60
      
      if (hours > 0) {
        return `${hours}小时${minutes}分钟`
      } else if (minutes > 0) {
        return `${minutes}分钟${seconds}秒`
      } else {
        return `${seconds}秒`
      }
    })

    const lastUpdateTime = computed(() => {
      return currentTime.value.format('HH:mm:ss')
    })

    const currentIP = computed(() => {
      const ip = systemStatus.value.ip_info
      if (!ip) return '获取中...'
      
      if (ip.using_proxy && ip.proxy_host) {
        return `${ip.proxy_host}:${ip.proxy_port}`
      }
      
      return ip.ip || '未知'
    })

    const proxyRotationEnabled = computed(() => {
      return systemStatus.value.proxy_rotation_enabled || false
    })

    const ipInfo = computed(() => {
      return systemStatus.value.ip_info || {}
    })

    // 任务统计方法
    const getTaskCount = (status) => {
      return allTasks.value.filter(task => task.status === status).length
    }

    const getTaskPercentage = (status) => {
      const total = allTasks.value.length
      if (total === 0) return 0
      
      const count = getTaskCount(status)
      return Math.round((count / total) * 100)
    }

    // 操作方法
    const refreshSystemStatus = () => {
      websocketService.getSystemStatus()
      ElMessage.success('正在刷新系统状态...')
    }

    const rotateIP = async () => {
      try {
        rotating.value = true
        
        const response = await axios.post('http://localhost:5001/api/system/rotate-ip')
        
        if (response.data.success) {
          ElMessage.success('IP切换成功')
          // 刷新系统状态以获取新的IP信息
          setTimeout(() => {
            refreshSystemStatus()
          }, 1000)
        } else {
          ElMessage.error('IP切换失败')
        }
        
      } catch (error) {
        console.error('IP rotation failed:', error)
        ElMessage.error('IP切换请求失败')
      } finally {
        rotating.value = false
      }
    }

    // 生命周期
    onMounted(() => {
      // 定时更新当前时间
      timer.value = setInterval(() => {
        currentTime.value = dayjs()
      }, 1000)
      
      // 初始获取系统状态
      refreshSystemStatus()
    })

    onUnmounted(() => {
      if (timer.value) {
        clearInterval(timer.value)
      }
    })

    return {
      // Icons
      DataLine,
      VideoPlay,
      Grid,
      Connection,
      Refresh,
      RefreshRight,
      
      // Reactive data
      rotating,
      
      // Computed
      isConnected,
      systemStatus,
      uptime,
      lastUpdateTime,
      currentIP,
      proxyRotationEnabled,
      ipInfo,
      
      // Methods
      getTaskCount,
      getTaskPercentage,
      refreshSystemStatus,
      rotateIP
    }
  }
}
</script>

<style scoped>
.system-status h3 {
  margin-bottom: 20px;
  color: #2c3e50;
}

.status-cards {
  margin-bottom: 20px;
}

.status-card {
  height: 100px;
}

.stat-item {
  display: flex;
  align-items: center;
  height: 100%;
}

.stat-icon {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 15px;
  font-size: 24px;
  color: white;
}

.stat-icon.total {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.stat-icon.active {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.stat-icon.concurrent {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.stat-icon.connection {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}

.stat-icon.connection.connected {
  background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
}

.stat-content {
  flex: 1;
}

.stat-number {
  font-size: 28px;
  font-weight: bold;
  color: #2c3e50;
  line-height: 1;
}

.stat-label {
  font-size: 14px;
  color: #8e8e93;
  margin-top: 5px;
}

.info-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ip-address {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-weight: bold;
  color: #2c3e50;
}

.task-distribution {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.distribution-item {
  display: flex;
  align-items: center;
  gap: 15px;
}

.distribution-label {
  min-width: 80px;
  font-weight: 500;
  color: #2c3e50;
}

.distribution-count {
  min-width: 30px;
  text-align: center;
  font-weight: bold;
  color: #2c3e50;
}

:deep(.el-progress-bar) {
  flex: 1;
}
</style>