<template>
  <el-dialog
    v-model="dialogVisible"
    title="创建新任务"
    width="600px"
    :before-close="handleClose"
  >
    <el-form 
      :model="formData" 
      :rules="rules" 
      ref="formRef"
      label-width="120px"
    >
      <el-form-item label="任务名称" prop="name">
        <el-input 
          v-model="formData.name" 
          placeholder="请输入任务名称"
        />
      </el-form-item>

      <el-form-item label="选择产品" prop="selected_product">
        <el-select 
          v-model="formData.selected_product" 
          placeholder="选择iPhone产品"
          style="width: 100%"
          @change="onProductChange"
        >
          <el-option
            v-for="product in productOptions.products"
            :key="product"
            :label="product"
            :value="product"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="产品URL" prop="url">
        <el-input 
          v-model="formData.url" 
          placeholder="产品URL将自动填充"
          type="textarea"
          :rows="2"
          :readonly="true"
        />
        <div class="url-hint">
          <el-text size="small" type="info">
            选择产品后将自动填充正确的URL
          </el-text>
        </div>
      </el-form-item>

      <el-divider>产品配置</el-divider>

      <el-form-item label="产品型号" prop="product_config.model">
        <el-select 
          v-model="formData.product_config.model" 
          placeholder="选择产品型号"
          style="width: 100%"
        >
          <el-option
            v-for="model in productOptions.models"
            :key="model"
            :label="model"
            :value="model"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="存储容量" prop="product_config.storage">
        <el-select 
          v-model="formData.product_config.storage" 
          placeholder="选择存储容量"
          style="width: 100%"
        >
          <el-option
            v-for="storage in productOptions.storages"
            :key="storage"
            :label="storage"
            :value="storage"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="颜色/材质" prop="product_config.finish">
        <el-select 
          v-model="formData.product_config.finish" 
          placeholder="选择颜色/材质"
          style="width: 100%"
        >
          <el-option
            v-for="finish in productOptions.finishes"
            :key="finish"
            :label="finish"
            :value="finish"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="以旧换新" prop="product_config.trade_in">
        <el-select 
          v-model="formData.product_config.trade_in" 
          placeholder="选择以旧换新选项"
          style="width: 100%"
        >
          <el-option
            v-for="option in productOptions.trade_in_options"
            :key="option"
            :label="option"
            :value="option"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="付款方式" prop="product_config.payment">
        <el-select 
          v-model="formData.product_config.payment" 
          placeholder="选择付款方式"
          style="width: 100%"
        >
          <el-option
            v-for="payment in productOptions.payment_options"
            :key="payment"
            :label="payment"
            :value="payment"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="AppleCare+" prop="product_config.apple_care">
        <el-select 
          v-model="formData.product_config.apple_care" 
          placeholder="选择AppleCare+选项"
          style="width: 100%"
        >
          <el-option
            v-for="care in productOptions.apple_care_options"
            :key="care"
            :label="care"
            :value="care"
          />
        </el-select>
      </el-form-item>

      <el-divider>高级选项</el-divider>

      <el-form-item label="任务优先级">
        <el-select 
          v-model="formData.priority" 
          placeholder="选择优先级"
          style="width: 100%"
        >
          <el-option label="低" :value="1" />
          <el-option label="中" :value="2" />
          <el-option label="高" :value="3" />
        </el-select>
      </el-form-item>

      <el-form-item label="使用代理">
        <el-switch
          v-model="formData.use_proxy"
          active-text="启用IP轮换"
          inactive-text="使用本地IP"
        />
      </el-form-item>

      <el-divider>账号配置</el-divider>

      <el-form-item label="Apple ID" prop="account_config.email">
        <el-input
          v-model="formData.account_config.email"
          placeholder="请输入Apple ID邮箱"
          type="email"
        />
      </el-form-item>

      <el-form-item label="密码" prop="account_config.password">
        <el-input
          v-model="formData.account_config.password"
          placeholder="请输入Apple ID密码"
          type="password"
          show-password
        />
      </el-form-item>

      <el-form-item label="电话号码" prop="account_config.phone_number">
        <el-input
          v-model="formData.account_config.phone_number"
          placeholder="请输入英国电话号码 (如: +447700900000)"
        />
        <div class="phone-hint">
          <el-text size="small" type="info">
            请输入英国格式的电话号码，以+44开头
          </el-text>
        </div>
      </el-form-item>

      <el-form-item label="礼品卡配置">
        <el-card class="gift-card-section">
          <div class="gift-card-header">
            <span>礼品卡列表</span>
            <el-button 
              type="primary" 
              size="small"
              @click="addGiftCard"
              :icon="Plus"
            >
              添加礼品卡
            </el-button>
          </div>
          
          <div v-if="formData.gift_cards.length === 0" class="no-gift-cards">
            暂无礼品卡配置
          </div>
          
          <div 
            v-for="(card, index) in formData.gift_cards" 
            :key="index"
            class="gift-card-item"
          >
            <el-input 
              v-model="card.number" 
              placeholder="礼品卡号码"
              style="margin-right: 10px; flex: 1;"
            />
            <el-input 
              v-model="card.pin" 
              placeholder="PIN码"
              style="margin-right: 10px; width: 120px;"
            />
            <el-button 
              type="danger" 
              size="small"
              @click="removeGiftCard(index)"
              :icon="Delete"
            />
          </div>
        </el-card>
      </el-form-item>

      <el-form-item label="自动启动">
        <el-switch 
          v-model="formData.enabled"
          active-text="创建后立即启动"
          inactive-text="创建后等待手动启动"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button 
          type="primary" 
          @click="handleSubmit"
          :loading="submitting"
        >
          创建任务
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useStore } from 'vuex'
import { ElMessage } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import axios from 'axios'

export default {
  name: 'TaskConfig',
  props: {
    visible: {
      type: Boolean,
      default: false
    }
  },
  emits: ['close', 'create'],
  setup(props, { emit }) {
    const store = useStore()
    const formRef = ref()
    const submitting = ref(false)

    const dialogVisible = computed({
      get: () => props.visible,
      set: (value) => {
        if (!value) {
          emit('close')
        }
      }
    })

    // 表单数据
    const formData = reactive({
      name: '',
      url: '',
      selected_product: '', // New field for selected product
      product_config: {
        model: '',
        storage: '',
        finish: '',
        trade_in: 'No trade-in',
        payment: 'Buy',
        apple_care: 'No AppleCare+ Coverage'
      },
      account_config: {
        email: '',
        password: '',
        phone_number: '+447700900000'  // 默认英国号码
      },
      priority: 2,
      use_proxy: false,
      gift_cards: [],
      enabled: true
    })

    // 验证规则
    const rules = {
      name: [
        { required: true, message: '请输入任务名称', trigger: 'blur' }
      ],
      'selected_product': [
        { required: true, message: '请选择产品', trigger: 'change' }
      ],
      'product_config.model': [
        { required: true, message: '请选择产品型号', trigger: 'change' }
      ],
      'product_config.storage': [
        { required: true, message: '请选择存储容量', trigger: 'change' }
      ],
      'product_config.finish': [
        { required: true, message: '请选择颜色/材质', trigger: 'change' }
      ],
      'account_config.email': [
        { required: true, message: '请输入Apple ID邮箱', trigger: 'blur' },
        { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
      ],
      'account_config.password': [
        { required: true, message: '请输入Apple ID密码', trigger: 'blur' },
        { min: 6, message: '密码长度至少6位', trigger: 'blur' }
      ],
      'account_config.phone_number': [
        { required: true, message: '请输入电话号码', trigger: 'blur' },
        { pattern: /^\+44\d{10}$/, message: '请输入正确的英国电话号码格式 (+44xxxxxxxxxx)', trigger: 'blur' }
      ]
    }

    // 产品选项
    const productOptions = computed(() => store.getters.getProductOptions)

    // 方法
    const addGiftCard = () => {
      formData.gift_cards.push({
        number: '',
        pin: ''
      })
    }

    const removeGiftCard = (index) => {
      formData.gift_cards.splice(index, 1)
    }

    const handleClose = () => {
      resetForm()
      emit('close')
    }

    const handleSubmit = async () => {
      try {
        const valid = await formRef.value.validate()
        if (!valid) return

        submitting.value = true

        // 验证礼品卡信息
        for (const card of formData.gift_cards) {
          if (!card.number || !card.pin) {
            ElMessage.error('请填写完整的礼品卡信息')
            submitting.value = false
            return
          }
        }

        // 提交任务创建请求
        emit('create', { ...formData })
        
        // 重置表单
        resetForm()
        
      } catch (error) {
        console.error('Form validation failed:', error)
      } finally {
        submitting.value = false
      }
    }

    const resetForm = () => {
      formData.name = ''
      formData.url = ''
      formData.selected_product = '' // Reset selected product
      formData.product_config = {
        model: '',
        storage: '',
        finish: '',
        trade_in: 'No trade-in',
        payment: 'Buy',
        apple_care: 'No AppleCare+ Coverage'
      }
      formData.account_config = {
        email: '',
        password: '',
        phone_number: '+447700900000'  // 默认英国号码
      }
      formData.priority = 2
      formData.use_proxy = false
      formData.gift_cards = []
      formData.enabled = true
      
      if (formRef.value) {
        formRef.value.clearValidate()
      }
    }

    const loadProductOptions = async () => {
      try {
        const response = await axios.get('http://localhost:5001/api/config/product-options')
        store.dispatch('setProductOptions', response.data)
      } catch (error) {
        console.error('Failed to load product options:', error)
        ElMessage.error('加载产品配置选项失败')
      }
    }

    const onProductChange = (value) => {
      // 使用API返回的产品URL映射
      const productUrls = productOptions.value.product_urls;
      if (productUrls && productUrls[value]) {
        formData.url = productUrls[value];
        formData.name = value; // 自动填充任务名称
      }
    }

    // 监听对话框显示状态
    watch(() => props.visible, (newValue) => {
      if (newValue) {
        loadProductOptions()
      }
    })

    onMounted(() => {
      loadProductOptions()
    })

    return {
      // Icons
      Plus,
      Delete,
      
      // Reactive data
      dialogVisible,
      formRef,
      formData,
      rules,
      submitting,
      productOptions,
      
      // Methods
      addGiftCard,
      removeGiftCard,
      handleClose,
      handleSubmit,
      onProductChange // Expose the new method
    }
  }
}
</script>

<style scoped>
.gift-card-section {
  margin: 0;
}

.gift-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.gift-card-item {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.no-gift-cards {
  text-align: center;
  color: #8e8e93;
  padding: 20px;
}

.url-hint {
  margin-top: 5px;
  text-align: right;
}

.phone-hint {
  margin-top: 5px;
  text-align: right;
}

:deep(.el-divider__text) {
  font-weight: 600;
  color: #2c3e50;
}
</style>