<template>
  <div class="test-gift-cards">
    <h2>🎁 多张礼品卡功能测试</h2>
    
    <div class="gift-cards-container">
      <div v-for="(card, index) in giftCards" :key="index" class="gift-card-item">
        <div class="card-header">
          <h3>礼品卡 {{ index + 1 }}</h3>
          <button v-if="giftCards.length > 1" @click="removeCard(index)" class="remove-btn">删除</button>
        </div>
        
        <div class="card-form">
          <div class="form-group">
            <label>礼品卡号码 (16位字母数字):</label>
            <input 
              type="text" 
              v-model="card.code" 
              @input="formatCode(index, $event)"
              placeholder="如：X7YVTGTLVR8FJ54Z"
              maxlength="16"
              class="code-input"
            />
          </div>
          
          <div class="form-group">
            <label>备注:</label>
            <textarea 
              v-model="card.note"
              placeholder="可选备注信息"
              rows="2"
              maxlength="100"
            ></textarea>
          </div>
        </div>
      </div>
    </div>
    
    <div class="actions">
      <button v-if="giftCards.length < 8" @click="addCard" class="add-btn">
        + 添加礼品卡 ({{ giftCards.length }}/8)
      </button>
      <div v-else class="max-limit">已达到最大数量限制 (8张)</div>
      
      <button @click="submitCards" class="submit-btn">提交所有礼品卡</button>
      <button @click="clearAll" class="clear-btn">清空所有</button>
    </div>
    
    <div v-if="result" class="result">
      <h3>提交结果：</h3>
      <pre>{{ result }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const giftCards = ref([
  { code: '', note: '' }
])

const result = ref('')

const addCard = () => {
  if (giftCards.value.length < 8) {
    giftCards.value.push({ code: '', note: '' })
  }
}

const removeCard = (index) => {
  if (giftCards.value.length > 1) {
    giftCards.value.splice(index, 1)
  }
}

const formatCode = (index, event) => {
  const value = event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').substring(0, 16)
  giftCards.value[index].code = value
}

const clearAll = () => {
  giftCards.value = [{ code: '', note: '' }]
  result.value = ''
}

const submitCards = async () => {
  const validCards = giftCards.value.filter(card => 
    card.code && card.code.trim().length === 16
  )

  if (validCards.length === 0) {
    alert('请至少输入一张有效的礼品卡号码')
    return
  }

  const submitData = {
    cards: validCards.map(card => ({
      code: card.code.toUpperCase(),
      note: card.note
    }))
  }

  result.value = JSON.stringify(submitData, null, 2)
  console.log('提交的礼品卡数据:', submitData)
}
</script>

<style scoped>
.test-gift-cards {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
  font-family: Arial, sans-serif;
}

.gift-card-item {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 15px;
  margin: 15px 0;
  background: #f9f9f9;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.card-header h3 {
  margin: 0;
  color: #409eff;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: bold;
}

.code-input, textarea {
  width: 100%;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-sizing: border-box;
}

.code-input {
  text-transform: uppercase;
  font-family: monospace;
}

.actions {
  text-align: center;
  margin: 20px 0;
}

.add-btn, .submit-btn, .clear-btn {
  margin: 5px;
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.add-btn {
  background: #409eff;
  color: white;
}

.submit-btn {
  background: #67c23a;
  color: white;
}

.clear-btn {
  background: #f56c6c;
  color: white;
}

.remove-btn {
  background: #f56c6c;
  color: white;
  border: none;
  padding: 5px 10px;
  border-radius: 4px;
  cursor: pointer;
}

.max-limit {
  color: #909399;
  font-size: 14px;
  margin: 10px 0;
}

.result {
  margin-top: 20px;
  padding: 15px;
  background: #f0f9ff;
  border: 1px solid #b3d8ff;
  border-radius: 4px;
}

.result pre {
  background: #fff;
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
}
</style>
