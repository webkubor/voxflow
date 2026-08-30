<template>
  <div class="tab-content-container">
    <!-- 模型未就绪警告 -->
    <div v-if="!modelStatus.base.ready && !modelStatus.base.downloading" class="warn-banner">
      ⚠️ <strong>Base 基础大模型未下载</strong> — 请在终端先跑 <code>./install.sh</code> 下载模型，否则剧本合成无法运行。
    </div>

    <!-- 顶部剧本配置表单 -->
    <div class="form-container dialogue-meta-card">
      <n-form :model="form" layout="vertical">
        <n-grid :cols="3" :x-gap="16">
          <n-grid-item>
            <n-form-item label="📂 项目唯一标识 (英文/拼音)">
              <n-input v-model:value="form.project_name" placeholder="例如：jianghu_anfang_reveal" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item label="🎭 剧目名称 (Title)">
              <n-input v-model:value="form.title" placeholder="例如：无厘头暗坊" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item label="🎭 全局情绪控制优先">
              <div class="switch-control">
                <n-switch v-model:value="form.emotion_priority" />
                <span class="switch-tip">开启后，剧本内每行默认强力匹配情绪标签</span>
              </div>
            </n-form-item>
          </n-grid-item>
        </n-grid>
      </n-form>
    </div>

    <!-- 动态行编辑区 -->
    <div class="lines-section-header">
      <span>🎬 剧本台词行 (共 {{ form.lines.length }} 句)</span>
      <n-button type="primary" size="small" secondary @click="addLine">
        ➕ 添加台词行
      </n-button>
    </div>

    <div class="lines-list">
      <div v-for="(line, idx) in form.lines" :key="idx" class="line-card-wrapper">
        <div class="line-index-badge">#{{ idx + 1 }}</div>
        
        <n-card class="line-edit-card" size="small" :bordered="true">
          <n-grid :cols="24" :x-gap="12">
            <!-- 角色与台词核心输入 -->
            <n-grid-item :span="6">
              <n-form-item label="👤 选择配音角色" size="small">
                <n-select 
                  v-model:value="line.persona" 
                  :options="personaOptions" 
                  placeholder="请选择音色..." 
                />
              </n-form-item>
            </n-grid-item>
            
            <n-grid-item :span="14">
              <n-form-item label="📝 角色台词台词">
                <n-input 
                  v-model:value="line.text" 
                  type="textarea"
                  :rows="2"
                  placeholder="在此处输入该角色的台词..." 
                />
              </n-form-item>
            </n-grid-item>

            <!-- 操作按钮 -->
            <n-grid-item :span="4" class="line-actions-cell">
              <n-button-group size="small">
                <n-button circle secondary @click="moveUp(idx)" :disabled="idx === 0" title="上移">
                  ⬆
                </n-button>
                <n-button circle secondary @click="moveDown(idx)" :disabled="idx === form.lines.length - 1" title="下移">
                  ⬇
                </n-button>
                <n-button circle secondary @click="duplicateLine(idx)" title="复制">
                  📋
                </n-button>
                <n-button circle type="error" secondary @click="removeLine(idx)" title="删除">
                  🗑️
                </n-button>
              </n-button-group>
            </n-grid-item>
          </n-grid>

          <!-- 高级微调选项 (折叠收纳) -->
          <n-collapse arrow-placement="right" class="line-advanced-collapse">
            <n-collapse-item name="advanced" title="🛠️ 角色演技与细节后处理微调">
              <n-grid :cols="4" :x-gap="12">
                <n-grid-item>
                  <n-form-item label="🗣️ 语气细节描述">
                    <n-input v-model:value="line.tone" placeholder="例如：语速偏慢，低声沉吟" />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item label="🎭 情绪控制标签">
                    <n-input v-model:value="line.emotion" placeholder="例如：Sad、Anger" />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item label="⚡ 独立情绪优先">
                    <n-switch v-model:value="line.emotion_priority" style="margin-top: 8px;" />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item label="💾 独立输出文件名 (可选)">
                    <n-input v-model:value="line.output_name" placeholder="例如：line_1.wav" />
                  </n-form-item>
                </n-grid-item>
              </n-grid>
            </n-collapse-item>
          </n-collapse>
        </n-card>
      </div>

      <!-- 空态指示 -->
      <div v-if="form.lines.length === 0" class="empty-lines" @click="addLine">
        📭 暂无台词行，点击此处快速添加第一句台词
      </div>
    </div>

    <!-- 底部总控区 -->
    <div class="dialogue-footer">
      <n-space>
        <n-button secondary @click="importConfig">
          📂 载入本地样例剧本
        </n-button>
      </n-space>
      
      <n-button 
        type="primary" 
        size="large"
        :loading="submitting" 
        :disabled="submitting || form.lines.length === 0 || !modelStatus.base.ready" 
        @click="submitDialogue"
      >
        🎭 一键合成多角色剧场配音
      </n-button>
    </div>
  </div>
</template>

<script setup>
/**
 * 剧本模式 / 多角色对话合成选项卡
 * 职责：提供可视化剧本编辑台，支持添加、删除、重排及配置单行高级调音，提交到异步剧本任务队列
 * API 来源：POST /api/dialogue
 */
import { ref, reactive, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useCapabilitiesStore } from '../stores/capabilities';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import { useVoicesStore } from '../stores/voices';

const { personas } = storeToRefs(useVoicesStore());
const { modelStatus } = useCapabilitiesStore();
const { loadDialogueSample, submitDialogue: submitDialogueTask } = useSynthStore();
const { showToast, showLoading, hideLoading } = useTasksStore();

const submitting = ref(false);

const form = reactive({
  project_name: 'vox_dialogue_project',
  title: '无厘头剧场',
  type: 'dialogue',
  emotion_priority: false,
  lines: [
    {
      role: '',
      persona: '',
      text: '',
      tone: '',
      emotion: '',
      emotion_priority: false,
      output_name: ''
    }
  ]
});

// 将 personas 格式化为 Select 组件所需的 options
const personaOptions = computed(() => {
  return Object.entries(personas.value || {}).map(([key, p]) => ({
    label: `${p.name} (${key})`,
    value: key
  }));
});

const addLine = () => {
  form.lines.push({
    role: '',
    persona: '',
    text: '',
    tone: '',
    emotion: '',
    emotion_priority: false,
    output_name: ''
  });
};

const removeLine = (idx) => {
  form.lines.splice(idx, 1);
};

const duplicateLine = (idx) => {
  const line = form.lines[idx];
  form.lines.splice(idx + 1, 0, JSON.parse(JSON.stringify(line)));
};

const moveUp = (idx) => {
  if (idx === 0) return;
  const temp = form.lines[idx];
  form.lines[idx] = form.lines[idx - 1];
  form.lines[idx - 1] = temp;
};

const moveDown = (idx) => {
  if (idx === form.lines.length - 1) return;
  const temp = form.lines[idx];
  form.lines[idx] = form.lines[idx + 1];
  form.lines[idx + 1] = temp;
};

// 载入本地 dialogue.json 作为样例
const importConfig = async () => {
  showLoading('正在载入本地样例剧本...');
  try {
    await loadDialogueSample(); // 保留原有 /api/scripts 探测请求
    // 原实现仅用脚本列表接口确认服务可用，随后填充内置样例。
    form.project_name = 'xingchi_reveal';
    form.title = '无厘头暗坊';
    form.emotion_priority = true;
    form.lines = [
      {
        role: 'demo_narrator',
        persona: 'demo_narrator',
        text: '名门讲道义，皇权讲法度，可这暗坊的影子里，只认‘价值’。 ... 宁观尘想借孤山的剑，慕夕歌要窥天下的局。 ... 殊不知跨过这道槛，两人便已从看客，成了这死局里…… 最先祭旗的棋子。',
        tone: '无厘头、机灵、带点夸张反差喜感，节奏灵活。‘价值’二字轻微停顿后抖包袱感，‘棋子’二字收尾带调侃意味。',
        emotion: '夸张、调侃、反差喜剧、轻微破音感但不要失真',
        emotion_priority: true,
        output_name: 'jianghu_anfang_1.wav'
      }
    ];
    showToast('本地样例剧本已载入！', 'success');
  } catch (e) {
    showToast('载入失败', 'error');
  } finally {
    hideLoading();
  }
};

const submitDialogue = async () => {
  if (form.lines.length === 0) {
    showToast('剧本中至少需要有一行台词！', 'warning');
    return;
  }
  
  // 校验每行
  for (let i = 0; i < form.lines.length; i++) {
    const line = form.lines[i];
    // 后端 DialogueMode 认的是 line.role 或者 line.persona
    line.role = line.persona;
    if (!line.persona) {
      showToast(`第 ${i+1} 行未选择配音角色！`, 'warning');
      return;
    }
    if (!line.text.trim()) {
      showToast(`第 ${i+1} 行台词不能为空！`, 'warning');
      return;
    }
  }

  submitting.value = true;
  try {
    await submitDialogueTask(form);
  } catch (e) {
    showToast('合成失败: ' + e.message, 'error');
  } finally {
    submitting.value = false;
  }
};
</script>

<style scoped>
.tab-content-container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.warn-banner {
  background-color: rgba(240, 160, 32, 0.1);
  border: 1px solid var(--vf-gold);
  border-radius: var(--vf-radius-sm);
  color: var(--vf-gold);
  padding: 10px 15px;
  font-size: 13px;
  margin-bottom: 16px;
}

.dialogue-meta-card {
  background-color: var(--vf-bg-2);
  border: 1px solid var(--vf-bg-4);
  border-radius: var(--vf-radius-md);
  padding: 16px;
  margin-bottom: 20px;
}

.switch-control {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 34px;
}

.switch-tip {
  font-size: 11px;
  color: var(--vf-text-3);
}

.lines-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.lines-list {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 20px;
}

.line-card-wrapper {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.line-index-badge {
  background-color: var(--vf-bg-4);
  color: var(--vf-text-2);
  font-size: 12px;
  font-weight: 700;
  padding: 4px 8px;
  border-radius: var(--vf-radius-sm);
  margin-top: 10px;
  min-width: 24px;
  text-align: center;
}

.line-edit-card {
  flex: 1;
  background-color: var(--vf-bg-1);
  border-color: var(--vf-bg-4);
  border-radius: var(--vf-radius-md);
}

.line-actions-cell {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  height: 80px;
}

.line-advanced-collapse {
  margin-top: 8px;
  border-top: 1px dashed var(--vf-border);
  padding-top: 8px;
}

.empty-lines {
  border: 2px dashed var(--vf-bg-4);
  border-radius: var(--vf-radius-lg);
  padding: 40px;
  text-align: center;
  color: var(--vf-text-3);
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}

.empty-lines:hover {
  border-color: var(--vf-primary);
  color: var(--vf-text-2);
}

.dialogue-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--vf-bg-4);
  padding-top: 16px;
}
</style>
