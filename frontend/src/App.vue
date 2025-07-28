<template>
  <div id="app">
    <el-container style="height: 100vh;">
      <!-- 顶部导航栏 -->
      <el-header class="header">
        <div class="header-left">
          <h2>🍎 Apple Bot System</h2>
        </div>
        <div class="header-right">
          <el-badge 
            :value="systemStatus.active_tasks" 
            type="primary" 
            class="status-badge"
          >
            <el-button 
              :type="isConnected ? 'success' : 'danger'" 
              size="small"
              @click="handleConnectionToggle"
            >
              {{ isConnected ? 'Connected' : 'Disconnected' }}
            </el-button>
          </el-badge>
          
          <el-button 
            type="primary" 
            @click="showCreateTaskDialog = true"
          >
            创建任务
          </el-button>
        </div>
      </el-header>

      <el-container>
        <!-- 侧边栏 -->
        <el-aside width="200px" class="sidebar">
          <el-menu 
            default-active="tasks" 
            class="menu"
            @select="handleMenuSelect"
          >
            <el-menu-item index="tasks">
              <span>任务列表</span>
            </el-menu-item>
            <el-menu-item index="running">
              <span>运行中 ({{ runningTasksCount }})</span>
            </el-menu-item>
            <el-menu-item index="completed">
              <span>已完成 ({{ completedTasksCount }})</span>
            </el-menu-item>
            <el-menu-item index="failed">
              <span>失败 ({{ failedTasksCount }})</span>
            </el-menu-item>
            <el-menu-item index="accounts">
              <span>账号管理</span>
            </el-menu-item>
            <el-menu-item index="system">
              <span>系统状态</span>
            </el-menu-item>
          </el-menu>
        </el-aside>

        <!-- 主内容区 -->
        <el-main class="main-content">
          <TaskList 
            v-if="currentView === 'tasks'" 
            :tasks="allTasks"
            :title="'所有任务'"
          />
          <TaskList 
            v-else-if="currentView === 'running'" 
            :tasks="runningTasks"
            :title="'运行中的任务'"
          />
          <TaskList 
            v-else-if="currentView === 'completed'" 
            :tasks="completedTasks"
            :title="'已完成的任务'"
          />
          <TaskList
            v-else-if="currentView === 'failed'"
            :tasks="failedTasks"
            :title="'失败的任务'"
          />
          <AccountManagement v-else-if="currentView === 'accounts'" />
          <SystemStatus v-else-if="currentView === 'system'" />
        </el-main>
      </el-container>
    </el-container>

    <!-- 创建任务对话框 -->
    <TaskConfig 
      :visible="showCreateTaskDialog"
      @close="showCreateTaskDialog = false"
      @create="handleTaskCreate"
    />
  </div>
</template>

<script>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useStore } from 'vuex'
import { ElMessage } from 'element-plus'

import websocketService from './services/websocket.js'
import TaskList from './components/TaskList.vue'
import TaskConfig from './components/TaskConfig.vue'
import SystemStatus from './components/SystemStatus.vue'
import AccountManagement from './components/AccountManagement.vue'

export default {
  name: 'App',
  components: {
    TaskList,
    TaskConfig,
    SystemStatus,
    AccountManagement
  },
  setup() {
    const store = useStore()
    const showCreateTaskDialog = ref(false)
    const currentView = ref('tasks')

    // 计算属性
    const isConnected = computed(() => store.getters.isConnected)
    const systemStatus = computed(() => store.getters.getSystemStatus)
    const allTasks = computed(() => store.getters.getTasks)
    const runningTasks = computed(() => 
      store.getters.getTasks.filter(task => 
        task.status === 'running' || task.status === 'pending'
      )
    )
    const completedTasks = computed(() => store.getters.getCompletedTasks)
    const failedTasks = computed(() => store.getters.getFailedTasks)

    // 任务数量统计
    const runningTasksCount = computed(() => runningTasks.value.length)
    const completedTasksCount = computed(() => completedTasks.value.length)
    const failedTasksCount = computed(() => failedTasks.value.length)

    // 方法
    const handleMenuSelect = (index) => {
      currentView.value = index
    }

    const handleConnectionToggle = () => {
      if (isConnected.value) {
        websocketService.disconnect()
        ElMessage.info('已断开连接')
      } else {
        websocketService.init(store)
        ElMessage.success('正在重新连接...')
      }
    }

    const handleTaskCreate = (taskData) => {
      websocketService.createTask(taskData)
      showCreateTaskDialog.value = false
      ElMessage.success('任务创建请求已发送')
    }

    // 生命周期钩子
    onMounted(() => {
      // 初始化WebSocket连接
      websocketService.init(store)
      
      // 定期获取系统状态
      const statusInterval = setInterval(() => {
        if (isConnected.value) {
          websocketService.getSystemStatus()
        }
      }, 5000)
      
      // 存储定时器ID以便清理
      window.statusInterval = statusInterval
    })

    onUnmounted(() => {
      // 清理定时器
      if (window.statusInterval) {
        clearInterval(window.statusInterval)
      }
      
      // 断开WebSocket连接
      websocketService.disconnect()
    })

    return {
      // Reactive data
      showCreateTaskDialog,
      currentView,
      
      // Computed
      isConnected,
      systemStatus,
      allTasks,
      runningTasks,
      completedTasks,
      failedTasks,
      runningTasksCount,
      completedTasksCount,
      failedTasksCount,
      
      // Methods
      handleMenuSelect,
      handleConnectionToggle,
      handleTaskCreate
    }
  }
}
</script>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  padding: 0 20px;
}

.header-left h2 {
  margin: 0;
  color: #2c3e50;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 15px;
}

.status-badge {
  margin-right: 10px;
}

.sidebar {
  background-color: #f8f9fa;
  border-right: 1px solid #e9ecef;
}

.menu {
  border: none;
  background-color: transparent;
}

.main-content {
  padding: 20px;
  background-color: #ffffff;
}

#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
</style>