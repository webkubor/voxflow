<template>
  <n-modal 
    :show="show" 
    preset="card" 
    style="width: 500px;" 
    title="注册新音色"
    :bordered="false"
    @update:show="closeModal"
  >
    <n-form :model="addForm" label-placement="left" label-width="80">
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
        <!-- ⚠️ n-form-item 的内容区是横向 flex：直接放两个兄弟节点，
             它们会各自成为并排的 flex 子项、被挤成竖排。必须包一层。
             （同一个坑今天在作品看板的详情区已经踩过一次） -->
        <div class="ref-audio-col">
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
            <Icon name="folder" size="lg" class="upload-icon" />
            <p>点击选择 或 拖拽 WAV/MP3 音频文件到此处</p>
            <span class="sub-tip">建议长度 3-15 秒，波形完整无杂音</span>
          </div>
          
          <div v-else class="selected-file-info" @click.stop>
            <Icon name="music" size="sm" class="audio-file-icon" />
            <div class="file-meta">
              <span class="file-name">{{ addForm.audioFile.name }}</span>
              <span class="file-size">{{ formatBytes(addForm.audioFile.size) }}</span>
            </div>
            <n-button type="error" text size="small" @click="addForm.audioFile = null">
              清除
            </n-button>
          </div>
        </div>
        <!-- 直接录：克隆自己的声音本来不该先去别的软件录一段再回来传文件。
             浏览器自带 MediaRecorder，localhost 就是安全上下文，够用。 -->
        <div class="record-row">
          <button
            class="record-btn"
            :class="{ recording }"
            type="button"
            @click="recording ? stopRecord() : startRecord()"
          >
            <Icon :name="recording ? 'pause' : 'voice'" size="sm" />
            <span>{{ recording ? `停止录音 ${recSec}s` : '直接录一段' }}</span>
          </button>
          <span class="sub-tip">
            {{ recording ? '正常语速念一段话，10 秒左右最好' : '不用先去别处录好再传文件' }}
          </span>
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
import Icon from './Icon.vue';
/**
 * 注册添加音色弹窗
 * 职责：支持表单信息填写，接收本地音频文件（支持点击及拖放上传），并提交 Multipart 上传
 * API 来源：POST /api/personas/add
 */
import { ref, reactive, computed } from 'vue';
import { useTasksStore } from '../stores/tasks';
import { useVoicesStore } from '../stores/voices';

const props = defineProps({
  show: {
    type: Boolean,
    required: true
  }
});

const emit = defineEmits(['update:show']);

const { addPersona } = useVoicesStore();
const { showToast, showLoading, hideLoading } = useTasksStore();

const dragOver = ref(false);
const fileInput = ref(null);

const addForm = reactive({
  key: '',
  name: '',
  instruction: '',
  audioFile: null
});

/**
 * 音色 Key 自动生成，不再让人自己编。
 *
 * 后端要的是个文件名安全的标识（前端原本还卡 /^[a-z0-9_]+$/）——
 * 而中文显示名转不出合法英文 ID，于是每个人都得停下来想一个
 * 「my_narrator」这样的东西。那一步对使用者零价值：
 * 界面上从头到尾显示的都是「显示名称」，Key 只有程序自己看。
 *
 * 用时间戳生成，天然唯一、天然合法。
 */
const autoKey = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `voice_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
};

// ── 直接录音 ────────────────────────────────────────────
const recording = ref(false);
const recSec = ref(0);
let mediaRecorder = null;
let recTimer = null;

const startRecord = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mediaRecorder.onstop = () => {
      // 停掉轨道，否则浏览器标签页会一直挂着录音指示灯
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      // 后端按扩展名判类型，webm 不在白名单里会被当 wav 存 —— 给个它认识的名字
      const ext = (mediaRecorder.mimeType || '').includes('ogg') ? 'ogg' : 'm4a';
      addForm.audioFile = new File([blob], `录音_${Date.now()}.${ext}`, { type: blob.type });
    };
    mediaRecorder.start();
    recording.value = true;
    recSec.value = 0;
    recTimer = setInterval(() => { recSec.value += 1; if (recSec.value >= 30) stopRecord(); }, 1000);
  } catch (e) {
    // 拒绝授权、没有麦克风、或非安全上下文都会走到这里
    showToast(`录音打不开：${e?.message || e}。也可以直接拖一个音频文件进来`, 'warning');
  }
};

const stopRecord = () => {
  clearInterval(recTimer);
  recording.value = false;
  if (mediaRecorder?.state === 'recording') mediaRecorder.stop();
};

// 表单校验 —— Key 已自动生成，不再是用户要填的东西
const isFormValid = computed(() => {
  return (
    addForm.name.trim() &&
    addForm.audioFile
  );
});

const closeModal = () => {
  // 关弹窗必须停录音 —— 不停的话麦克风轨道还开着，
  // 浏览器标签页上的录音指示灯会一直亮，人以为被偷录。
  stopRecord();
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

  const keyVal = addForm.key.trim() || autoKey();   // 没手填就自动生成
  const nameVal = addForm.name.trim();
  const instVal = addForm.instruction.trim();

  const formData = new FormData();
  formData.append('key', keyVal);
  formData.append('name', nameVal);
  formData.append('instruction', instVal);
  formData.append('audio', addForm.audioFile);

  showLoading('正在上传参考音频并注册音色...');
  try {
    await addPersona(formData);
    showToast('音色注册成功', 'success');
    closeModal();
  } catch (e) {
    showToast(e.message || '注册音色接口异常', 'error');
  } finally {
    hideLoading();
  }
};
</script>

<style scoped>
.ref-audio-col { flex: 1; min-width: 0; }
.record-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.record-btn {
  flex: none;
  white-space: nowrap;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--vf-border, #333);
  background: transparent; color: inherit; font-size: 13px;
}
.record-btn.recording { border-color: #ff5c5c; color: #ff5c5c; }

.file-drop-zone {
  width: 100%;
  border: 1px dashed #444;
  border-radius: 6px;
  background-color: var(--vf-bg-1);
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
  border-color: var(--vf-ok);
  background-color: rgba(54, 173, 106, 0.04);
}

.drop-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.upload-icon {
  /* SVG 图标不吃 font-size（Icon 组件用 width/height 属性），
     这里显式给尺寸；原来是 emoji 靠 28px 字号撑起来的。 */
  width: 28px;
  height: 28px;
  color: var(--vf-text-3);
  margin-bottom: 6px;
}

.drop-placeholder p {
  margin: 0;
  font-size: 13px;
  color: var(--vf-text-2);
}

.sub-tip {
  font-size: 11px;
  color: var(--vf-text-3);
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
  width: 20px;
  height: 20px;
  color: var(--vf-primary);
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
  color: var(--vf-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-size {
  font-size: 11px;
  color: var(--vf-text-3);
}

.modal-footer-btns {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
