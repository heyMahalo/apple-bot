<template>
  <div class="test-purchase">
    <div class="header">
      <h1>🧪 Apple 购买流程测试</h1>
      <p>测试 USB-C to USB Adapter 购买流程</p>
    </div>

    <div class="test-config">
      <h2>测试配置</h2>
      <div class="config-grid">
        <div class="config-item">
          <label>测试产品:</label>
          <div class="product-info">
            <strong>USB-C to USB Adapter</strong>
            <br>
            <small>https://www.apple.com/uk/shop/product/MW5L3ZM/A/usb-c-to-usb-adapter</small>
          </div>
        </div>
        
        <div class="config-item">
          <label>测试账号:</label>
          <div class="account-info">
            <strong>Shawnstandard16@yahoo.com</strong>
            <br>
            <small>密码: Pewqf996</small>
          </div>
        </div>
        
        <div class="config-item">
          <label>测试礼品卡:</label>
          <div class="gift-card-info">
            <strong>XH49MCQ2JF2G98XT</strong>
            <br>
            <small>16位礼品卡号码</small>
          </div>
        </div>
      </div>
    </div>

    <div class="test-controls">
      <h2>测试控制</h2>
      <div class="button-group">
        <button 
          @click="startTest" 
          :disabled="isRunning"
          class="btn btn-primary"
        >
          {{ isRunning ? '测试进行中...' : '🚀 开始购买流程测试' }}
        </button>
        
        <button 
          @click="stopTest" 
          :disabled="!isRunning"
          class="btn btn-danger"
        >
          🛑 停止测试
        </button>
        
        <button 
          @click="clearLogs"
          class="btn btn-secondary"
        >
          🗑️ 清空日志
        </button>
      </div>
    </div>

    <div class="test-status" v-if="currentTask">
      <h2>测试状态</h2>
      <div class="status-grid">
        <div class="status-item">
          <label>任务ID:</label>
          <span>{{ currentTask.id }}</span>
        </div>
        
        <div class="status-item">
          <label>当前状态:</label>
          <span :class="getStatusClass(currentTask.status)">
            {{ getStatusText(currentTask.status) }}
          </span>
        </div>
        
        <div class="status-item">
          <label>当前步骤:</label>
          <span>{{ currentTask.current_step || '未开始' }}</span>
        </div>
        
        <div class="status-item">
          <label>进度:</label>
          <div class="progress-bar">
            <div 
              class="progress-fill" 
              :style="{ width: (currentTask.progress || 0) + '%' }"
            ></div>
            <span class="progress-text">{{ currentTask.progress || 0 }}%</span>
          </div>
        </div>
      </div>

      <!-- 醒目的礼品卡状态显示 -->
      <div v-if="giftCardStatus" class="gift-card-status-banner" :class="giftCardStatus.type">
        <div class="status-icon">
          <span v-if="giftCardStatus.type === 'success'">✅</span>
          <span v-else-if="giftCardStatus.type === 'error'">❌</span>
          <span v-else-if="giftCardStatus.type === 'insufficient'">⚠️</span>
          <span v-else>🎁</span>
        </div>
        <div class="status-content">
          <div class="status-title">{{ giftCardStatus.title }}</div>
          <div class="status-message">{{ giftCardStatus.message }}</div>
        </div>
        <button v-if="giftCardStatus.type !== 'success'" @click="showGiftCardDialog = true" class="add-card-btn">
          {{ giftCardStatus.type === 'insufficient' ? '补充余额' : '重新输入' }}
        </button>
      </div>
    </div>

    <div class="test-logs">
      <h2>测试日志</h2>
      <div class="logs-container" ref="logsContainer">
        <div 
          v-for="(log, index) in logs" 
          :key="index"
          :class="['log-entry', `log-${log.level}`]"
        >
          <span class="log-time">{{ formatTime(log.timestamp) }}</span>
          <span class="log-level">{{ log.level.toUpperCase() }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
        
        <div v-if="logs.length === 0" class="no-logs">
          暂无日志信息
        </div>
      </div>
    </div>

    <!-- 礼品卡输入对话框 -->
    <div v-if="showGiftCardDialog" class="modal-overlay" @click="closeGiftCardDialog">
      <div class="modal-content" @click.stop>
        <h3>🎁 输入礼品卡信息</h3>

        <!-- 显示余额不足信息 -->
        <div v-if="insufficientBalanceInfo" class="insufficient-balance-warning">
          <div class="warning-icon">⚠️</div>
          <div class="warning-content">
            <h4>余额不足</h4>
            <p>当前礼品卡余额不足，还需要 <strong>{{ insufficientBalanceInfo.currency }}{{ insufficientBalanceInfo.remaining_amount }}</strong></p>
            <p>请输入更多礼品卡来补足余额：</p>
          </div>
        </div>

        <!-- 普通礼品卡输入提示 -->
        <p v-else>系统检测到需要输入礼品卡，请输入测试礼品卡号码：</p>
        
        <div class="gift-card-input">
          <label>礼品卡号码:</label>
          <input 
            v-model="giftCardCode"
            type="text"
            placeholder="XH49MCQ2JF2G98XT"
            maxlength="16"
            class="gift-card-field"
          />
        </div>
        
        <div class="modal-buttons">
          <button @click="closeGiftCardDialog" class="btn btn-secondary">
            取消
          </button>
          <button @click="submitGiftCard" class="btn btn-primary">
            提交礼品卡
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import axios from 'axios'
import { io } from 'socket.io-client'

// 响应式数据
const isRunning = ref(false)
const currentTask = ref(null)
const logs = ref([])
const showGiftCardDialog = ref(false)
const giftCardCode = ref('XH49MCQ2JF2G98XT')
const insufficientBalanceInfo = ref(null)
const giftCardStatus = ref(null)
const logsContainer = ref(null)

// WebSocket连接
let socket = null

// 测试配置
const testConfig = {
  name: 'Belkin Secure Holder 购买测试',
  url: 'https://www.apple.com/uk/shop/product/HNPW2ZM/A/belkin-secure-holder-with-strap-for-airtag-white?fnode=3e01bb7dbb2ab8ca8e16c9b8b41e08dfc9de2813df2d463c62955a50059d0457875db51e9b81ee4a679c3c28c27651817798dbe3dabea05b5bcd387360348d4b30990a26e6fabd0ee742a6774ff91d166cfaa4ea29bd1f95d6242edbf147acfb',
  account: {
    email: 'Shawnstandard16@yahoo.com',
    password: 'Pewqf996'
  },
  gift_card: 'XH49MCQ2JF2G98XT'
}

// 初始化WebSocket连接
const initWebSocket = () => {
  socket = io('http://localhost:5001')
  
  socket.on('connect', () => {
    addLog('WebSocket连接成功', 'info')
  })
  
  socket.on('task_update', (data) => {
    if (currentTask.value && data.task_id === currentTask.value.id) {
      currentTask.value = { ...currentTask.value, ...data }
      addLog(`任务状态更新: ${data.status}`, 'info')
    }
  })
  
  socket.on('task_log', (data) => {
    if (currentTask.value && data.task_id === currentTask.value.id) {
      addLog(data.message, data.level || 'info')
    }
  })
  
  socket.on('gift_card_required', (data) => {
    if (currentTask.value && data.task_id === currentTask.value.id) {
      addLog('系统请求输入礼品卡', 'warning')
      showGiftCardDialog.value = true
    }
  })

  socket.on('insufficient_balance', (data) => {
    if (currentTask.value && data.task_id === currentTask.value.id) {
      const message = `余额不足，还需要 ${data.currency}${data.remaining_amount}`
      addLog(message, 'warning')
      insufficientBalanceInfo.value = {
        remaining_amount: data.remaining_amount,
        currency: data.currency,
        message: data.message
      }

      // 更新醒目的礼品卡状态显示
      giftCardStatus.value = {
        type: 'insufficient',
        title: '礼品卡余额不足',
        message: `还需要 ${data.currency}${data.remaining_amount}`
      }

      // 更新任务状态显示
      if (currentTask.value) {
        currentTask.value.status = 'waiting_for_gift_card'
        currentTask.value.statusMessage = `余额不足，还需要 ${data.currency}${data.remaining_amount}`
      }

      showGiftCardDialog.value = true
    }
  })

  // 监听礼品卡错误事件
  socket.on('gift_card_error', (data) => {
    if (currentTask.value && data.task_id === currentTask.value.id) {
      const message = `礼品卡错误: ${data.error_message}`
      addLog(message, 'error')

      // 更新醒目的礼品卡状态显示
      giftCardStatus.value = {
        type: 'error',
        title: '礼品卡错误',
        message: data.error_message
      }

      showGiftCardDialog.value = true
    }
  })

  // 监听礼品卡成功事件
  socket.on('gift_card_success', (data) => {
    if (currentTask.value && data.task_id === currentTask.value.id) {
      const message = `礼品卡应用成功: ${data.message}`
      addLog(message, 'success')

      // 更新醒目的礼品卡状态显示
      giftCardStatus.value = {
        type: 'success',
        title: '礼品卡应用成功',
        message: data.message
      }

      // 3秒后自动隐藏成功状态
      setTimeout(() => {
        if (giftCardStatus.value && giftCardStatus.value.type === 'success') {
          giftCardStatus.value = null
        }
      }, 3000)
    }
  })
  
  socket.on('disconnect', () => {
    addLog('WebSocket连接断开', 'warning')
  })
}

// 开始测试
const startTest = async () => {
  try {
    isRunning.value = true
    addLog('开始创建测试任务...', 'info')
    
    const response = await axios.post('http://localhost:5001/api/tasks', {
      name: testConfig.name,
      url: testConfig.url,
      account_email: testConfig.account.email,
      account_password: testConfig.account.password,
      type: 'test_purchase',
      product_config: {
        model: 'test-product',
        finish: 'default',
        storage: 'default',
        trade_in: 'No trade-in',
        payment: 'Buy',
        apple_care: 'No AppleCare+ Coverage'
      },
      account_config: {
        email: testConfig.account.email,
        password: testConfig.account.password,
        phone_number: '07700900000'
      },
      gift_cards: [],
      priority: 3
    })
    
    if (response.data.success) {
      currentTask.value = response.data.task
      addLog(`任务创建成功，ID: ${currentTask.value.id}`, 'success')
      
      // 开始执行任务
      await executeTask()
    } else {
      throw new Error(response.data.message || '任务创建失败')
    }
    
  } catch (error) {
    addLog(`测试启动失败: ${error.message}`, 'error')
    isRunning.value = false
  }
}

// 执行任务
const executeTask = async () => {
  try {
    addLog('开始执行购买流程...', 'info')
    
    const response = await axios.post(`http://localhost:5001/api/tasks/${currentTask.value.id}/execute`)
    
    if (response.data.success) {
      addLog('任务执行请求发送成功', 'success')
    } else {
      throw new Error(response.data.message || '任务执行失败')
    }
    
  } catch (error) {
    addLog(`任务执行失败: ${error.message}`, 'error')
    isRunning.value = false
  }
}

// 停止测试
const stopTest = async () => {
  try {
    if (currentTask.value) {
      await axios.post(`http://localhost:5001/api/tasks/${currentTask.value.id}/stop`)
      addLog('任务停止请求已发送', 'info')
    }
    
    isRunning.value = false
    currentTask.value = null
    
  } catch (error) {
    addLog(`停止任务失败: ${error.message}`, 'error')
  }
}

// 提交礼品卡
const submitGiftCard = async () => {
  try {
    if (!giftCardCode.value || giftCardCode.value.length !== 16) {
      addLog('请输入有效的16位礼品卡号码', 'error')
      return
    }
    
    const response = await axios.post(`http://localhost:5001/api/tasks/${currentTask.value.id}/gift-card`, {
      cards: [{
        code: giftCardCode.value.toUpperCase(),
        note: '测试礼品卡'
      }]
    })
    
    if (response.data.success) {
      addLog('礼品卡提交成功', 'success')
      showGiftCardDialog.value = false
    } else {
      throw new Error(response.data.message || '礼品卡提交失败')
    }
    
  } catch (error) {
    addLog(`礼品卡提交失败: ${error.message}`, 'error')
  }
}

// 关闭礼品卡对话框
const closeGiftCardDialog = () => {
  showGiftCardDialog.value = false
  insufficientBalanceInfo.value = null  // 清除余额不足信息
}

// 清空日志
const clearLogs = () => {
  logs.value = []
}

// 添加日志
const addLog = (message, level = 'info') => {
  logs.value.push({
    timestamp: new Date(),
    level,
    message
  })
  
  // 自动滚动到底部
  nextTick(() => {
    if (logsContainer.value) {
      logsContainer.value.scrollTop = logsContainer.value.scrollHeight
    }
  })
}

// 格式化时间
const formatTime = (timestamp) => {
  return timestamp.toLocaleTimeString()
}

// 获取状态样式类
const getStatusClass = (status) => {
  const statusMap = {
    'pending': 'status-pending',
    'running': 'status-running',
    'completed': 'status-completed',
    'failed': 'status-failed',
    'waiting_gift_card_input': 'status-waiting'
  }
  return statusMap[status] || 'status-unknown'
}

// 获取状态文本
const getStatusText = (status) => {
  const statusMap = {
    'pending': '等待中',
    'running': '运行中',
    'completed': '已完成',
    'failed': '失败',
    'waiting_gift_card_input': '等待礼品卡输入'
  }
  return statusMap[status] || status
}

// 生命周期
onMounted(() => {
  initWebSocket()
  addLog('测试页面初始化完成', 'info')
})

onUnmounted(() => {
  if (socket) {
    socket.disconnect()
  }
})
</script>

<style scoped>
.test-purchase {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.header {
  text-align: center;
  margin-bottom: 30px;
  padding: 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 12px;
}

.header h1 {
  margin: 0 0 10px 0;
  font-size: 2.5em;
}

.header p {
  margin: 0;
  opacity: 0.9;
}

.test-config, .test-controls, .test-status, .test-logs {
  background: white;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.test-config h2, .test-controls h2, .test-status h2, .test-logs h2 {
  margin: 0 0 20px 0;
  color: #333;
  border-bottom: 2px solid #f0f0f0;
  padding-bottom: 10px;
}

.config-grid, .status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

.config-item, .status-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-item label, .status-item label {
  font-weight: 600;
  color: #555;
}

.product-info, .account-info, .gift-card-info {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  border-left: 4px solid #007aff;
}

.button-group {
  display: flex;
  gap: 15px;
  flex-wrap: wrap;
}

.btn {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  min-width: 120px;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #007aff;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #0056b3;
  transform: translateY(-2px);
}

.btn-danger {
  background: #ff3b30;
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: #d70015;
  transform: translateY(-2px);
}

.btn-secondary {
  background: #8e8e93;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #6d6d70;
  transform: translateY(-2px);
}

.progress-bar {
  position: relative;
  width: 100%;
  height: 24px;
  background: #f0f0f0;
  border-radius: 12px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #34c759, #30d158);
  transition: width 0.3s ease;
  border-radius: 12px;
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 12px;
  font-weight: 600;
  color: #333;
}

.status-pending { color: #ff9500; }
.status-running { color: #007aff; }
.status-completed { color: #34c759; }
.status-failed { color: #ff3b30; }
.status-waiting { color: #ff9500; }
.status-waiting_for_gift_card { color: #ff6b35; }
.status-unknown { color: #8e8e93; }

.logs-container {
  max-height: 400px;
  overflow-y: auto;
  background: #1a1a1a;
  border-radius: 8px;
  padding: 15px;
}

.log-entry {
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 13px;
  line-height: 1.4;
}

.log-time {
  color: #8e8e93;
  min-width: 80px;
}

.log-level {
  min-width: 60px;
  font-weight: 600;
}

.log-info .log-level { color: #007aff; }
.log-success .log-level { color: #34c759; }
.log-warning .log-level { color: #ff9500; }
.log-error .log-level { color: #ff3b30; }

.log-message {
  color: #f2f2f7;
  flex: 1;
}

.no-logs {
  text-align: center;
  color: #8e8e93;
  font-style: italic;
  padding: 20px;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  padding: 30px;
  max-width: 500px;
  width: 90%;
  box-shadow: 0 10px 30px rgba(0,0,0,0.3);
}

.modal-content h3 {
  margin: 0 0 15px 0;
  color: #333;
}

.gift-card-input {
  margin: 20px 0;
}

.gift-card-input label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: #555;
}

.gift-card-field {
  width: 100%;
  padding: 12px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 16px;
  font-family: monospace;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.gift-card-field:focus {
  outline: none;
  border-color: #007aff;
}

.insufficient-balance-warning {
  display: flex;
  align-items: flex-start;
  background: #fff3cd;
  border: 1px solid #ffeaa7;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.warning-icon {
  font-size: 24px;
  margin-right: 12px;
  flex-shrink: 0;
}

.warning-content h4 {
  margin: 0 0 8px 0;
  color: #856404;
  font-size: 16px;
}

.warning-content p {
  margin: 4px 0;
  color: #856404;
  line-height: 1.4;
}

.warning-content strong {
  color: #d63384;
  font-weight: 600;
}

/* 醒目的礼品卡状态横幅 */
.gift-card-status-banner {
  display: flex;
  align-items: center;
  padding: 16px;
  margin: 16px 0;
  border-radius: 12px;
  border-left: 4px solid;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  animation: slideIn 0.3s ease-out;
}

.gift-card-status-banner.success {
  background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
  border-left-color: #28a745;
  color: #155724;
}

.gift-card-status-banner.error {
  background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
  border-left-color: #dc3545;
  color: #721c24;
}

.gift-card-status-banner.insufficient {
  background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
  border-left-color: #ffc107;
  color: #856404;
}

.gift-card-status-banner .status-icon {
  font-size: 24px;
  margin-right: 16px;
  flex-shrink: 0;
}

.gift-card-status-banner .status-content {
  flex: 1;
}

.gift-card-status-banner .status-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

.gift-card-status-banner .status-message {
  font-size: 14px;
  opacity: 0.9;
}

.gift-card-status-banner .add-card-btn {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-left: 16px;
}

.gift-card-status-banner .add-card-btn:hover {
  background: rgba(255, 255, 255, 1);
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.modal-buttons {
  display: flex;
  gap: 15px;
  justify-content: flex-end;
  margin-top: 25px;
}
</style>
