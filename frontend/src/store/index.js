import { createStore } from 'vuex'

export default createStore({
  state: {
    tasks: [],
    systemStatus: {
      total_tasks: 0,
      active_tasks: 0,
      max_concurrent: 3,
      connected: false
    },
    socket: null,
    productOptions: {
      models: [],
      finishes: [],
      storages: [],
      trade_in_options: [],
      payment_options: [],
      apple_care_options: []
    }
  },
  
  getters: {
    getTasks: (state) => state.tasks,
    getTaskById: (state) => (id) => {
      return state.tasks.find(task => task.id === id)
    },
    getActiveTasks: (state) => {
      return state.tasks.filter(task => 
        task.status === 'pending' || task.status === 'running'
      )
    },
    getCompletedTasks: (state) => {
      return state.tasks.filter(task => task.status === 'completed')
    },
    getFailedTasks: (state) => {
      return state.tasks.filter(task => task.status === 'failed')
    },
    isConnected: (state) => state.systemStatus.connected,
    getSystemStatus: (state) => state.systemStatus,
    getProductOptions: (state) => state.productOptions
  },
  
  mutations: {
    SET_TASKS(state, tasks) {
      state.tasks = tasks
    },
    
    ADD_TASK(state, task) {
      const existingIndex = state.tasks.findIndex(t => t.id === task.id)
      if (existingIndex >= 0) {
        state.tasks.splice(existingIndex, 1, task)
      } else {
        state.tasks.push(task)
      }
    },
    
    UPDATE_TASK(state, updatedTask) {
      const index = state.tasks.findIndex(task => task.id === updatedTask.id)
      if (index >= 0) {
        state.tasks.splice(index, 1, updatedTask)
      }
    },
    
    REMOVE_TASK(state, taskId) {
      const index = state.tasks.findIndex(task => task.id === taskId)
      if (index >= 0) {
        state.tasks.splice(index, 1)
      }
    },
    
    SET_SYSTEM_STATUS(state, status) {
      state.systemStatus = { ...state.systemStatus, ...status }
    },
    
    SET_CONNECTION_STATUS(state, connected) {
      state.systemStatus.connected = connected
    },
    
    SET_SOCKET(state, socket) {
      state.socket = socket
    },
    
    SET_PRODUCT_OPTIONS(state, options) {
      state.productOptions = options
    }
  },
  
  actions: {
    setTasks({ commit }, tasks) {
      commit('SET_TASKS', tasks)
    },
    
    addTask({ commit }, task) {
      commit('ADD_TASK', task)
    },
    
    updateTask({ commit }, task) {
      commit('UPDATE_TASK', task)
    },
    
    removeTask({ commit }, taskId) {
      commit('REMOVE_TASK', taskId)
    },
    
    setSystemStatus({ commit }, status) {
      commit('SET_SYSTEM_STATUS', status)
    },
    
    setConnectionStatus({ commit }, connected) {
      commit('SET_CONNECTION_STATUS', connected)
    },
    
    setSocket({ commit }, socket) {
      commit('SET_SOCKET', socket)
    },
    
    setProductOptions({ commit }, options) {
      commit('SET_PRODUCT_OPTIONS', options)
    }
  },
  
  modules: {}
})