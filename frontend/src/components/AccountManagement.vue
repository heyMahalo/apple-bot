<template>
  <div class="account-management">
    <div class="page-header">
      <h2>账号管理</h2>
      <el-button 
        type="primary" 
        @click="showCreateDialog = true"
        :icon="Plus"
      >
        添加账号
      </el-button>
    </div>

    <!-- 账号列表 -->
    <el-table 
      :data="accounts" 
      style="width: 100%"
      v-loading="loading"
    >
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="email" label="邮箱" min-width="200" />
      <el-table-column prop="phone_number" label="电话号码" width="180">
        <template #default="scope">
          {{ scope.row.phone_number || '+447700900000' }}
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="scope">
          {{ formatDate(scope.row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" width="100">
        <template #default="scope">
          <el-tag :type="scope.row.is_active ? 'success' : 'danger'">
            {{ scope.row.is_active ? '活跃' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="scope">
          <el-button 
            size="small" 
            @click="editAccount(scope.row)"
            :icon="Edit"
          >
            编辑
          </el-button>
          <el-button 
            size="small" 
            type="danger" 
            @click="deleteAccount(scope.row)"
            :icon="Delete"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑账号对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingAccount ? '编辑账号' : '添加账号'"
      width="500px"
    >
      <el-form 
        :model="accountForm" 
        :rules="accountRules" 
        ref="accountFormRef"
        label-width="100px"
      >
        <el-form-item label="邮箱" prop="email">
          <el-input 
            v-model="accountForm.email" 
            placeholder="请输入Apple ID邮箱"
            type="email"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input 
            v-model="accountForm.password" 
            placeholder="请输入Apple ID密码"
            type="password"
            show-password
          />
        </el-form-item>

        <el-form-item label="电话号码" prop="phone_number">
          <el-input 
            v-model="accountForm.phone_number" 
            placeholder="请输入英国电话号码 (如: +447700900000)"
          />
          <div class="phone-hint">
            <el-text size="small" type="info">
              请输入英国格式的电话号码，以+44开头
            </el-text>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button @click="cancelEdit">取消</el-button>
          <el-button 
            type="primary" 
            @click="saveAccount"
            :loading="saving"
          >
            {{ editingAccount ? '更新' : '创建' }}
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import axios from 'axios'

export default {
  name: 'AccountManagement',
  setup() {
    const accounts = ref([])
    const loading = ref(false)
    const saving = ref(false)
    const showCreateDialog = ref(false)
    const editingAccount = ref(null)
    const accountFormRef = ref()

    const accountForm = reactive({
      email: '',
      password: '',
      phone_number: '+447700900000'
    })

    const accountRules = {
      email: [
        { required: true, message: '请输入邮箱', trigger: 'blur' },
        { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
      ],
      password: [
        { required: true, message: '请输入密码', trigger: 'blur' },
        { min: 6, message: '密码长度至少6位', trigger: 'blur' }
      ],
      phone_number: [
        { required: true, message: '请输入电话号码', trigger: 'blur' },
        { pattern: /^\+44\d{10}$/, message: '请输入正确的英国电话号码格式 (+44xxxxxxxxxx)', trigger: 'blur' }
      ]
    }

    // 获取账号列表
    const fetchAccounts = async () => {
      loading.value = true
      try {
        const response = await axios.get('/api/accounts')
        console.log('获取到的账号数据:', response.data)
        accounts.value = response.data

        // 确保每个账号都有phone_number字段
        accounts.value = accounts.value.map(account => ({
          ...account,
          phone_number: account.phone_number || '+447700900000'
        }))

      } catch (error) {
        console.error('获取账号列表失败:', error)
        ElMessage.error('获取账号列表失败: ' + (error.response?.data?.error || error.message))
      } finally {
        loading.value = false
      }
    }

    // 格式化日期
    const formatDate = (dateString) => {
      if (!dateString) return '-'
      return new Date(dateString).toLocaleString('zh-CN')
    }

    // 编辑账号
    const editAccount = (account) => {
      editingAccount.value = account
      accountForm.email = account.email
      accountForm.password = '' // 不显示原密码
      accountForm.phone_number = account.phone_number || '+447700900000'
      showCreateDialog.value = true
    }

    // 保存账号
    const saveAccount = async () => {
      try {
        const valid = await accountFormRef.value.validate()
        if (!valid) return

        saving.value = true

        if (editingAccount.value) {
          // 更新账号
          await axios.put(`/api/accounts/${editingAccount.value.id}`, accountForm)
          ElMessage.success('账号更新成功')
        } else {
          // 创建账号
          await axios.post('/api/accounts', accountForm)
          ElMessage.success('账号创建成功')
        }

        showCreateDialog.value = false
        await fetchAccounts()
        resetForm()

      } catch (error) {
        ElMessage.error('保存失败: ' + (error.response?.data?.error || error.message))
      } finally {
        saving.value = false
      }
    }

    // 删除账号
    const deleteAccount = async (account) => {
      try {
        await ElMessageBox.confirm(
          `确定要删除账号 "${account.email}" 吗？`,
          '确认删除',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
          }
        )

        await axios.delete(`/api/accounts/${account.id}`)
        ElMessage.success('账号删除成功')
        await fetchAccounts()

      } catch (error) {
        if (error !== 'cancel') {
          ElMessage.error('删除失败: ' + (error.response?.data?.error || error.message))
        }
      }
    }

    // 取消编辑
    const cancelEdit = () => {
      showCreateDialog.value = false
      resetForm()
    }

    // 重置表单
    const resetForm = () => {
      editingAccount.value = null
      accountForm.email = ''
      accountForm.password = ''
      accountForm.phone_number = '+447700900000'
      if (accountFormRef.value) {
        accountFormRef.value.resetFields()
      }
    }

    onMounted(() => {
      fetchAccounts()
    })

    return {
      accounts,
      loading,
      saving,
      showCreateDialog,
      editingAccount,
      accountForm,
      accountRules,
      accountFormRef,
      fetchAccounts,
      formatDate,
      editAccount,
      saveAccount,
      deleteAccount,
      cancelEdit,
      resetForm,
      Plus,
      Edit,
      Delete
    }
  }
}
</script>

<style scoped>
.account-management {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  color: #303133;
}

.phone-hint {
  margin-top: 5px;
  text-align: right;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
