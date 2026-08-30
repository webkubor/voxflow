<template>
  <n-modal 
    :show="show" 
    preset="card" 
    style="width: 500px;" 
    title="🎙️ 注册新音色"
    :bordered="false"
    @update:show="closeModal"
  >
    <n-form :model="addForm" label-placement="left" label-width="80">
      <n-form-item label="音色 Key">
        <n-input 
          v-model:value="addForm.key" 
          placeholder="例如：my_narrator（限小写字母和下划线）" 
        />
      </n-form-item>
      
      <n-form-item label="显示名称">
        <n-input 
          v-model:value="addForm.name" 
          placeholder="例如：我的旁白音色" 
        />
      </n-form-item>
      
      <n-form-item label="音色描述">
        <n-input 
          v-model:value="addForm.instruction" 
          type="textarea"
          rows="2"
          placeholder="描述这个声音的语速、语气和特色，如：中年男子，沉稳磁性" 
        />
      </n-form-item>

      <n-form-item label="参考音频">
        <div 
          class="file-drop-zone"
          :class="{ 'is-dragover': dragOver }"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="handleFileDrop"
          @click="triggerFileSelect"
        >
          <input 
            ref="fileInput"
            type="file" 
            accept="audio/*" 
            style="display: none;" 
            @change="handleFileSelect"
          />
          
          <div v-if="!addForm.audioFile" class="drop-placeholder">
            <span class="upload-icon">📁</span>
            <p>点击选择 或 拖拽 WAV/MP3 音频文件到此处</p>
            <span class="sub-tip">建议长度 3-15 秒，波形完整无杂音</span>
          </div>
          
          <div v-else class="selected-file-info" @click.stop>
            <span class="audio-file-icon">🎵</span>
            <div class="file-meta">
              <span class="file-name">{{ addForm.audioFile.name }}</span>
              <span class="file-size">{{ formatBytes(addForm.audioFile.size) }}</span>
            </div>
            <n-button type="error" text size="small" @click="addForm.audioFile = null">
              清除
            </n-button>
          </div>
        </div>
      </n-form-item>
    </n-form>

    <template #footer>
      <div class="modal-footer-btns">
        <n-button @click="closeModal">取消</n-button>
        <n-button type="primary" :disabled="!isFormValid" @click="submitAdd">
          确认注册
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
/**
 * 注册添加音色弹窗
 * 职责：支持表单信息填写，接收本地音频文件（支持点击及拖放上传），并提交 Multipart 上传
 * API 来源：POST /api/personas/add
 */
import { ref, reactive, computed, inject } from 'vue';

const props = defineProps({
  show: {
    type: Boolean,
    required: true
  }
});

const emit = defineEmits(['update:show']);

const { loadPersonas, showToast, showLoading, hideLoading } = inject('actions');

const dragOver = ref(false);
const fileInput = ref(null);

const addForm = reactive({
  key: '',
  name: '',
  instruction: '',
  audioFile: null
});

// 表单校验
const isFormValid = computed(() => {
  return (
    addForm.key.trim() &&
    /^[a-z0-9_]+$/.test(addForm.key.trim()) &&
    addForm.name.trim() &&
    addForm.audioFile
  );
});

const closeModal = () => {
  addForm.key = '';
  addForm.name = '';
  addForm.instruction = '';
  addForm.audioFile = null;
  dragOver.value = false;
  emit('update:show', false);
};

const triggerFileSelect = () => {
  if (fileInput.value) {
    fileInput.value.click();
  }
};

const handleFileSelect = (e) => {
  const files = e.target.files;
  if (files && files.length > 0) {
    addForm.audioFile = files[0];
  }
};

const handleFileDrop = (e) => {
  dragOver.value = false;
  const files = e.dataTransfer.files;
  if (files && files.length > 0) {
    addForm.audioFile = files[0];
  }
};

const formatBytes = (bytes) => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const submitAdd = async () => {
  if (!isFormValid.value) return;

  const keyVal = addForm.key.trim();
  const nameVal = addForm.name.trim();
  const instVal = addForm.instruction.trim();

  const formData = new FormData();
  formData.append('key', keyVal);
  formData.append('name', nameVal);
  formData.append('instruction', instVal);
  formData.append('audio', addForm.audioFile);

  showLoading('正在上传参考音频并注册音色...');
  try {
    const res = await fetch('/api/personas/add', {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    hideLoading();
    if (data.status === 'ok') {
      showToast('音色注册成功', 'success');
      closeModal();
      await loadPersonas();
    } else {
      showToast(data.error || '注册失败', 'error');
    }
  } catch (e) {
    hideLoading();
    showToast('注册音色接口异常', 'error');
  }
};
</script>

<style scoped>
.file-drop-zone {
  width: 100%;
  border: 1px dashed #444;
  border-radius: 6px;
  background-color: #18181c;
  min-height: 120px;
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  box-sizing: border-box;
  padding: 15px;
  transition: border-color 0.2s, background-color 0.2s;
}

.file-drop-zone:hover,
.file-drop-zone.is-dragover {
  border-color: #36ad6a;
  background-color: rgba(54, 173, 106, 0.04);
}

.drop-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.upload-icon {
  font-size: 28px;
  margin-bottom: 6px;
}

.drop-placeholder p {
  margin: 0;
  font-size: 13px;
  color: #a0a0a5;
}

.sub-tip {
  font-size: 11px;
  color: #606065;
  margin-top: 4px;
}

.selected-file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  justify-content: space-between;
}

.audio-file-icon {
  font-size: 24px;
}

.file-meta {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.file-name {
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-size {
  font-size: 11px;
  color: #808085;
}

.modal-footer-btns {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
