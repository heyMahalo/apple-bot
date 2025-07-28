<template>
  <div class="task-list">
    <div class="task-list-header">
      <h3>{{ title }}</h3>
      <div class="task-stats">
        <el-tag>总计: {{ tasks.length }}</el-tag>
      </div>
    </div>

    <el-table 
      :data="tasks" 
      style="width: 100%" 
      :default-sort="{ prop: 'created_at', order: 'descending' }"
      @row-click="handleRowClick"
    >
      <el-table-column prop="config.name" label="任务名称" min-width="200">
        <template #default="scope">
          <div class="task-name">
            <strong>{{ scope.row.config.name }}</strong>
            <div class="task-url">{{ scope.row.config.url }}</div>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="status" label="状态" width="120">
        <template #default="scope">
          <el-tag 
            :type="getStatusType(scope.row.status)"
            size="small"
          >
            {{ getStatusText(scope.row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="current_step" label="当前步骤" width="150">
        <template #default="scope">
          <span v-if="scope.row.current_step">
            {{ getStepText(scope.row.current_step) }}
          </span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>

      <el-table-column prop="progress" label="进度" width="150">
        <template #default="scope">
          <el-progress 
            :percentage="scope.row.progress" 
            :status="getProgressStatus(scope.row.status)"
            :stroke-width="6"
          />
        </template>
      </el-table-column>

      <el-table-column label="产品配置" min-width="200">
        <template #default="scope">
          <div class="product-config">
            <div>型号: {{ scope.row.config.product_config.model }}</div>
            <div>容量: {{ scope.row.config.product_config.storage }}</div>
            <div>颜色: {{ scope.row.config.product_config.finish }}</div>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="created_at" label="创建时间" width="160">
        <template #default="scope">
          {{ formatTime(scope.row.created_at) }}
        </template>
      </el-table-column>

      <el-table-column label="操作" width="200" fixed="right">
        <template #default="scope">
          <div class="action-buttons">
            <el-button 
              v-if="scope.row.status === 'pending'"
              type="primary" 
              size="small"
              @click.stop="startTask(scope.row.id)"
              :icon="VideoPlay"
            >
              启动
            </el-button>

            <el-button 
              v-if="scope.row.status === 'running'"
              type="warning" 
              size="small"
              @click.stop="cancelTask(scope.row.id)"
              :icon="VideoPause"
            >
              取消
            </el-button>

            <el-button 
              type="info" 
              size="small"
              @click.stop="viewDetails(scope.row)"
              :icon="View"
            >
              详情
            </el-button>

            <el-popconfirm
              title="确定要删除这个任务吗？"
              @confirm="deleteTask(scope.row.id)"
            >
              <template #reference>
                <el-button 
                  type="danger" 
                  size="small"
                  @click.stop
                  :icon="Delete"
                >
                  删除
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- 任务详情对话框 -->
    <TaskStatus 
      :visible="showDetailDialog"
      :task="selectedTask"
      @close="showDetailDialog = false"
    />
  </div>
</template>

<script>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, VideoPause, View, Delete } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

import websocketService from '../services/websocket.js'
import TaskStatus from './TaskStatus.vue'

export default {
  name: 'TaskList',
  components: {
    TaskStatus
  },
  props: {
    tasks: {
      type: Array,
      default: () => []
    },
    title: {
      type: String,
      default: '任务列表'
    }
  },
  setup() {
    const showDetailDialog = ref(false)
    const selectedTask = ref(null)

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
        'initializing': '初始化',
        'navigating': '导航页面',
        'configuring_product': '配置产品',
        'adding_to_bag': '添加购物袋',
        'checkout': '结账',
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

    // 时间格式化
    const formatTime = (timeString) => {
      if (!timeString) return '-'
      return dayjs(timeString).format('MM-DD HH:mm')
    }

    // 任务操作方法
    const startTask = (taskId) => {
      websocketService.startTask(taskId)
      ElMessage.success('启动任务请求已发送')
    }

    const cancelTask = (taskId) => {
      websocketService.cancelTask(taskId)
      ElMessage.warning('取消任务请求已发送')
    }

    const deleteTask = (taskId) => {
      websocketService.deleteTask(taskId)
      ElMessage.success('删除任务请求已发送')
    }

    const viewDetails = (task) => {
      selectedTask.value = task
      showDetailDialog.value = true
    }

    const handleRowClick = (row) => {
      viewDetails(row)
    }

    return {
      // Icons
      VideoPlay,
      VideoPause,
      View,
      Delete,
      
      // Reactive data
      showDetailDialog,
      selectedTask,
      
      // Methods
      getStatusType,
      getStatusText,
      getStepText,
      getProgressStatus,
      formatTime,
      startTask,
      cancelTask,
      deleteTask,
      viewDetails,
      handleRowClick
    }
  }
}
</script>

<style scoped>
.task-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.task-list-header h3 {
  margin: 0;
  color: #2c3e50;
}

.task-stats {
  display: flex;
  gap: 10px;
}

.task-name {
  line-height: 1.4;
}

.task-url {
  font-size: 12px;
  color: #8e8e93;
  margin-top: 2px;
}

.product-config {
  font-size: 13px;
  line-height: 1.4;
}

.product-config div {
  margin-bottom: 2px;
}

.action-buttons {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.text-muted {
  color: #8e8e93;
}

:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-table__row:hover) {
  background-color: #f5f7fa;
}
</style>