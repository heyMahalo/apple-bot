<template>
  <el-dialog
    v-model="dialogVisible"
    :title="task ? `任务详情 - ${task.config.name}` : '任务详情'"
    width="800px"
    :before-close="handleClose"
  >
    <div v-if="task" class="task-detail">
      <!-- 基本信息 -->
      <el-card class="detail-card">
        <template #header>
          <div class="card-header">
            <span>基本信息</span>
            <el-tag 
              :type="getStatusType(task.status)"
              size="large"
            >
              {{ getStatusText(task.status) }}
            </el-tag>
          </div>
        </template>
        
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务ID">
            {{ task.id }}
          </el-descriptions-item>
          <el-descriptions-item label="任务名称">
            {{ task.config.name }}
          </el-descriptions-item>
          <el-descriptions-item label="产品URL" :span="2">
            <el-link :href="task.config.url" target="_blank" type="primary">
              {{ task.config.url }}
            </el-link>
          </el-descriptions-item>
          <el-descriptions-item label="当前步骤">
            {{ task.current_step ? getStepText(task.current_step) : '未开始' }}
          </el-descriptions-item>
          <el-descriptions-item label="进度">
            <el-progress 
              :percentage="task.progress" 
              :status="getProgressStatus(task.status)"
            />
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatTime(task.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ formatTime(task.started_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="完成时间" v-if="task.completed_at">
            {{ formatTime(task.completed_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="耗时" v-if="task.started_at">
            {{ getDuration(task.started_at, task.completed_at) }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 产品配置 -->
      <el-card class="detail-card">
        <template #header>
          <span>产品配置</span>
        </template>
        
        <el-descriptions :column="2" border>
          <el-descriptions-item label="产品型号">
            {{ task.config.product_config.model }}
          </el-descriptions-item>
          <el-descriptions-item label="存储容量">
            {{ task.config.product_config.storage }}
          </el-descriptions-item>
          <el-descriptions-item label="颜色/材质">
            {{ task.config.product_config.finish }}
          </el-descriptions-item>
          <el-descriptions-item label="以旧换新">
            {{ task.config.product_config.trade_in }}
          </el-descriptions-item>
          <el-descriptions-item label="付款方式">
            {{ task.config.product_config.payment }}
          </el-descriptions-item>
          <el-descriptions-item label="AppleCare+">
            {{ task.config.product_config.apple_care }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 任务配置 -->
      <el-card class="detail-card">
        <template #header>
          <span>任务配置</span>
        </template>
        
        <el-descriptions :column="2" border>
          <el-descriptions-item label="优先级">
            <el-tag :type="getPriorityType(task.config.priority)">
              {{ getPriorityText(task.config.priority) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="使用代理">
            <el-tag :type="task.config.use_proxy ? 'success' : 'info'">
              {{ task.config.use_proxy ? '是' : '否' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="启用状态">
            <el-tag :type="task.config.enabled ? 'success' : 'warning'">
              {{ task.config.enabled ? '已启用' : '已禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="礼品卡数量">
            {{ task.config.gift_cards ? task.config.gift_cards.length : 0 }} 张
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 错误信息 -->
      <el-card v-if="task.error_message" class="detail-card error-card">
        <template #header>
          <span>错误信息</span>
        </template>
        <el-alert
          :title="task.error_message"
          type="error"
          :closable="false"
          show-icon
        />
      </el-card>

      <!-- 执行日志 -->
      <el-card class="detail-card">
        <template #header>
          <div class="card-header">
            <span>执行日志</span>
            <el-button 
              size="small" 
              @click="refreshLogs"
              :icon="Refresh"
            >
              刷新
            </el-button>
          </div>
        </template>
        
        <div class="logs-container">
          <div 
            v-if="!task.logs || task.logs.length === 0" 
            class="no-logs"
          >
            暂无日志记录
          </div>
          
          <div 
            v-for="(log, index) in task.logs" 
            :key="index"
            class="log-item"
            :class="`log-${log.level}`"
          >
            <div class="log-time">
              {{ formatTime(log.timestamp) }}
            </div>
            <div class="log-level">
              <el-tag 
                :type="getLogLevelType(log.level)" 
                size="small"
              >
                {{ log.level.toUpperCase() }}
              </el-tag>
            </div>
            <div class="log-message">
              {{ log.message }}
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="handleClose">关闭</el-button>
        
        <el-button 
          v-if="task && task.status === 'pending'"
          type="primary"
          @click="startTask"
          :icon="VideoPlay"
        >
          启动任务
        </el-button>
        
        <el-button 
          v-if="task && task.status === 'running'"
          type="warning"
          @click="cancelTask"
          :icon="VideoPause"
        >
          取消任务
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, VideoPause, Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

import websocketService from '../services/websocket.js'

export default {
  name: 'TaskStatus',
  props: {
    visible: {
      type: Boolean,
      default: false
    },
    task: {
      type: Object,
      default: null
    }
  },
  emits: ['close'],
  setup(props, { emit }) {
    const dialogVisible = computed({
      get: () => props.visible,
      set: (value) => {
        if (!value) {
          emit('close')
        }
      }
    })

    // 状态相关方法
    const getStatusType = (status) => {
      const statusMap = {
        'pending': '',
        'running': 'warning',
        'completed': 'success',
        'failed': 'danger',
        'cancelled': 'info'
      }
      return statusMap[status] || ''
    }

    const getStatusText = (status) => {
      const statusMap = {
        'pending': '等待中',
        'running': '运行中',
        'completed': '已完成',
        'failed': '失败',
        'cancelled': '已取消'
      }
      return statusMap[status] || status
    }

    const getStepText = (step) => {
      const stepMap = {
        'initializing': '初始化浏览器',
        'navigating': '导航到产品页面',
        'configuring_product': '配置产品选项',
        'adding_to_bag': '添加到购物袋',
        'checkout': '进入结账流程',
        'applying_gift_card': '应用礼品卡',
        'finalizing': '完成购买'
      }
      return stepMap[step] || step
    }

    const getProgressStatus = (status) => {
      if (status === 'completed') return 'success'
      if (status === 'failed') return 'exception'
      if (status === 'running') return 'active'
      return ''
    }

    const getPriorityType = (priority) => {
      const priorityMap = {
        1: 'info',
        2: 'warning', 
        3: 'danger'
      }
      return priorityMap[priority] || 'info'
    }

    const getPriorityText = (priority) => {
      const priorityMap = {
        1: '低',
        2: '中',
        3: '高'
      }
      return priorityMap[priority] || '未知'
    }

    const getLogLevelType = (level) => {
      const levelMap = {
        'info': 'primary',
        'warning': 'warning',
        'error': 'danger',
        'debug': 'info'
      }
      return levelMap[level] || 'primary'
    }

    // 时间相关方法
    const formatTime = (timeString) => {
      if (!timeString) return '-'
      return dayjs(timeString).format('YYYY-MM-DD HH:mm:ss')
    }

    const getDuration = (startTime, endTime) => {
      if (!startTime) return '-'
      
      const start = dayjs(startTime)
      const end = endTime ? dayjs(endTime) : dayjs()
      const duration = end.diff(start, 'second')
      
      const hours = Math.floor(duration / 3600)
      const minutes = Math.floor((duration % 3600) / 60)
      const seconds = duration % 60
      
      if (hours > 0) {
        return `${hours}小时${minutes}分钟${seconds}秒`
      } else if (minutes > 0) {
        return `${minutes}分钟${seconds}秒`
      } else {
        return `${seconds}秒`
      }
    }

    // 操作方法
    const startTask = () => {
      if (props.task) {
        websocketService.startTask(props.task.id)
        ElMessage.success('启动任务请求已发送')
      }
    }

    const cancelTask = () => {
      if (props.task) {
        websocketService.cancelTask(props.task.id)
        ElMessage.warning('取消任务请求已发送')
      }
    }

    const refreshLogs = () => {
      if (props.task) {
        websocketService.getTaskDetail(props.task.id)
        ElMessage.success('刷新日志请求已发送')
      }
    }

    const handleClose = () => {
      emit('close')
    }

    return {
      // Icons
      VideoPlay,
      VideoPause,
      Refresh,
      
      // Computed
      dialogVisible,
      
      // Methods
      getStatusType,
      getStatusText,
      getStepText,
      getProgressStatus,
      getPriorityType,
      getPriorityText,
      getLogLevelType,
      formatTime,
      getDuration,
      startTask,
      cancelTask,
      refreshLogs,
      handleClose
    }
  }
}
</script>

<style scoped>
.task-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.detail-card {
  margin-bottom: 20px;
}

.detail-card:last-child {
  margin-bottom: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.error-card {
  border-color: #f56c6c;
}

.logs-container {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 10px;
  background-color: #fafafa;
}

.no-logs {
  text-align: center;
  color: #8e8e93;
  padding: 20px;
}

.log-item {
  display: flex;
  align-items: flex-start;
  margin-bottom: 8px;
  padding: 8px;
  border-radius: 4px;
  background-color: #ffffff;
  border-left: 3px solid #e4e7ed;
}

.log-item.log-error {
  border-left-color: #f56c6c;
  background-color: #fef0f0;
}

.log-item.log-warning {
  border-left-color: #e6a23c;
  background-color: #fdf6ec;
}

.log-item.log-info {
  border-left-color: #409eff;
  background-color: #ecf5ff;
}

.log-time {
  font-size: 12px;
  color: #8e8e93;
  white-space: nowrap;
  margin-right: 10px;
  min-width: 140px;
}

.log-level {
  margin-right: 10px;
}

.log-message {
  flex: 1;
  word-break: break-word;
}

:deep(.el-descriptions__label) {
  font-weight: 600;
}
</style>