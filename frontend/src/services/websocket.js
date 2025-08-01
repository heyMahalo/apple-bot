import { io } from 'socket.io-client'

class WebSocketService {
  constructor() {
    this.socket = null
    this.store = null
    this.isConnected = false
    this.reconnectAttempts = 0
    this.maxReconnectAttempts = 5
  }

  init(store, serverUrl = 'http://localhost:5001') {
    this.store = store

    this.socket = io(serverUrl, {
      transports: ['websocket', 'polling'],
      timeout: 20000,
      forceNew: true
    })

    this.setupEventListeners()
    this.store.commit('SET_SOCKET', this.socket)

    // 🚀 自动加入所有任务的实时更新
    this.socket.on('connect', () => {
      console.log('✅ Socket.IO连接成功，准备加入任务房间')
      this.joinAllTaskRooms()
    })

    return this.socket
  }

  setupEventListeners() {
    // 连接事件
    this.socket.on('connect', () => {
      console.log('Connected to server')
      this.isConnected = true
      this.reconnectAttempts = 0
      this.store.commit('SET_CONNECTION_STATUS', true)
    })

    this.socket.on('disconnect', () => {
      console.log('Disconnected from server')
      this.isConnected = false
      this.store.commit('SET_CONNECTION_STATUS', false)
    })

    this.socket.on('connect_error', (error) => {
      console.error('Connection error:', error)
      this.handleReconnect()
    })

    // 任务相关事件
    this.socket.on('initial_tasks', (data) => {
      console.log('Received initial tasks:', data.tasks)
      this.store.commit('SET_TASKS', data.tasks)
    })

    this.socket.on('task_created', (task) => {
      console.log('Task created:', task)
      this.store.commit('ADD_TASK', task)
    })

    this.socket.on('task_update', (task) => {
      console.log('Task updated:', task)
      this.store.commit('UPDATE_TASK', task)
    })

    // 🚀 SOTA事件监听
    this.socket.on('task_status_update', (data) => {
      console.log('📊 SOTA任务状态更新:', data)
      this.store.commit('UPDATE_TASK_STATUS', {
        taskId: data.task_id,
        status: data.status,
        progress: data.progress,
        message: data.message
      })
    })

    this.socket.on('step_update', (data) => {
      console.log('🔄 SOTA步骤更新:', data)
      this.store.commit('UPDATE_TASK_STEP', {
        taskId: data.task_id,
        step: data.step,
        progress: data.progress,
        message: data.message
      })
    })

    this.socket.on('task_log', (data) => {
      console.log('📝 SOTA任务日志:', data)
      this.store.commit('ADD_TASK_LOG', {
        taskId: data.task_id,
        log: {
          level: data.level,
          message: data.message,
          timestamp: data.timestamp
        }
      })
    })

    // 🚀 交互式提示事件
    this.socket.on('prompt_required', (data) => {
      console.log('💬 收到交互式提示:', data)
      this.store.commit('SET_PROMPT', data)
    })

    // 🚀 任务快照事件
    this.socket.on('task_snapshot', (data) => {
      console.log('📸 收到任务快照:', data)
      this.store.commit('UPDATE_TASK_SNAPSHOT', data)
    })

    // 🚀 网关连接事件
    this.socket.on('connected', (data) => {
      console.log('🚀 Socket.IO网关连接成功:', data)
    })

    this.socket.on('joined_task', (data) => {
      console.log('✅ 已加入任务房间:', data)
    })

    this.socket.on('task_deleted', (data) => {
      console.log('Task deleted:', data.task_id)
      this.store.commit('REMOVE_TASK', data.task_id)
    })

    this.socket.on('tasks_list', (data) => {
      console.log('Tasks list received:', data.tasks)
      this.store.commit('SET_TASKS', data.tasks)
    })

    // 系统状态事件
    this.socket.on('system_status', (status) => {
      console.log('System status:', status)
      this.store.commit('SET_SYSTEM_STATUS', status)
    })

    // 错误处理
    this.socket.on('error', (error) => {
      console.error('Socket error:', error)
      this.$message.error(error.message || 'WebSocket error occurred')
    })

    // 任务操作响应
    this.socket.on('task_create_success', (data) => {
      console.log('Task created successfully:', data)
    })

    this.socket.on('task_create_error', (error) => {
      console.error('Task creation failed:', error)
    })

    this.socket.on('task_start_success', (data) => {
      console.log('Task started successfully:', data)
    })

    this.socket.on('task_start_error', (error) => {
      console.error('Task start failed:', error)
    })

    this.socket.on('task_cancel_success', (data) => {
      console.log('Task cancelled successfully:', data)
    })

    this.socket.on('task_cancel_error', (error) => {
      console.error('Task cancellation failed:', error)
    })
  }

  handleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`)
      
      setTimeout(() => {
        if (!this.isConnected) {
          this.socket.connect()
        }
      }, 3000 * this.reconnectAttempts) // 递增延迟
    } else {
      console.error('Max reconnection attempts reached')
    }
  }

  // API方法
  createTask(taskData) {
    if (this.socket && this.isConnected) {
      this.socket.emit('create_task', taskData)
    } else {
      console.error('Socket not connected')
    }
  }

  startTask(taskId) {
    if (this.socket && this.isConnected) {
      this.socket.emit('start_task', { task_id: taskId })
    } else {
      console.error('Socket not connected')
    }
  }

  cancelTask(taskId) {
    if (this.socket && this.isConnected) {
      this.socket.emit('cancel_task', { task_id: taskId })
    } else {
      console.error('Socket not connected')
    }
  }

  deleteTask(taskId) {
    if (this.socket && this.isConnected) {
      this.socket.emit('delete_task', { task_id: taskId })
    } else {
      console.error('Socket not connected')
    }
  }

  getTasks() {
    if (this.socket && this.isConnected) {
      this.socket.emit('get_tasks')
    } else {
      console.error('Socket not connected')
    }
  }

  getTaskDetail(taskId) {
    if (this.socket && this.isConnected) {
      this.socket.emit('get_task_detail', { task_id: taskId })
    } else {
      console.error('Socket not connected')
    }
  }

  getSystemStatus() {
    if (this.socket && this.isConnected) {
      this.socket.emit('get_system_status')
    } else {
      console.error('Socket not connected')
    }
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
      this.isConnected = false
    }
  }

  // 🚀 SOTA方法：加入所有任务房间
  joinAllTaskRooms() {
    if (!this.socket || !this.store) return

    const tasks = this.store.getters.getTasks
    tasks.forEach(task => {
      this.joinTaskRoom(task.id)
    })
  }

  // 🚀 加入特定任务房间
  joinTaskRoom(taskId) {
    if (!this.socket) return

    console.log(`🔗 加入任务房间: ${taskId}`)
    this.socket.emit('join_task', { task_id: taskId })
  }

  // 🚀 离开任务房间
  leaveTaskRoom(taskId) {
    if (!this.socket) return

    console.log(`🔗 离开任务房间: ${taskId}`)
    this.socket.emit('leave_task', { task_id: taskId })
  }

  // 🚀 提交礼品卡输入
  submitGiftCardInput(taskId, giftCardData) {
    if (!this.socket) return

    console.log(`🎁 提交礼品卡输入: ${taskId}`, giftCardData)
    this.socket.emit('gift_card_input', {
      task_id: taskId,
      gift_card_data: giftCardData
    })
  }
}

export default new WebSocketService()