<template>
  <div class="tab-content-container">
    <WarnBanner
      v-if="!modelStatus.base.ready && !modelStatus.base.downloading"
      type="warn"
      title="Base 基础大模型未下载"
      hint="请在终端先跑 ./install.sh 下载模型，否则剧本合成无法运行。"
    />

    <!-- 剧目元信息 -->
    <section class="meta-card">
      <div class="meta-grid">
        <div class="meta-cell">
          <label class="meta-label">📂 项目标识（英文/拼音）</label>
          <n-input v-model:value="form.project_name" placeholder="如：jianghu_anfang_reveal" />
        </div>
        <div class="meta-cell">
          <label class="meta-label">🎭 剧目名称</label>
          <n-input v-model:value="form.title" placeholder="如：无厘头暗坊" />
        </div>
        <div class="meta-cell">
          <label class="meta-label">🎭 全局情绪控制优先</label>
          <label class="switch-row">
            <n-switch v-model:value="form.emotion_priority" />
            <span class="switch-tip">开启后剧本内每行默认强力匹配情绪标签</span>
          </label>
        </div>
      </div>
    </section>

    <!-- 台词行 -->
    <div class="lines-head">
      <span class="lines-title">🎬 剧本台词</span>
      <span class="lines-count">共 {{ form.lines.length }} 句</span>
      <button class="add-line-btn" @click="addLine">
        <Icon name="plus" size="sm" />
        <span>添加台词行</span>
      </button>
    </div>

    <div class="lines-list">
      <article
        v-for="(line, idx) in form.lines"
        :key="idx"
        class="line-card"
      >
        <div class="line-index">#{{ idx + 1 }}</div>
        <div class="line-body">
          <div class="line-grid">
            <div class="line-persona">
              <label class="line-label">👤 配音角色</label>
              <n-select
                v-model:value="line.persona"
                :options="personaOptions"
                placeholder="选择音色..."
                size="small"
              />
            </div>
            <div class="line-text">
              <label class="line-label">📝 角色台词</label>
              <n-input
                v-model:value="line.text"
                type="textarea"
                :rows="2"
                placeholder="在此输入台词…"
              />
            </div>
          </div>

          <details class="line-advanced">
            <summary class="line-advanced-head">
              <Icon name="design" size="sm" />
              <span>演技与细节微调</span>
              <Icon name="chevron-down" size="sm" class="chevron" />
            </summary>
            <div class="line-advanced-body">
              <div class="form-cell">
                <label class="line-label">🗣️ 语气细节</label>
                <n-input v-model:value="line.tone" placeholder="如：语速偏慢，低声沉吟" />
              </div>
              <div class="form-cell">
                <label class="line-label">🎭 情绪控制</label>
                <n-input v-model:value="line.emotion" placeholder="如：Sad、Anger" />
              </div>
              <div class="form-cell">
                <label class="line-label">⚡ 独立情绪优先</label>
                <n-switch v-model:value="line.emotion_priority" />
              </div>
              <div class="form-cell">
                <label class="line-label">💾 输出文件名（可选）</label>
                <n-input v-model:value="line.output_name" placeholder="如：line_1.wav" />
              </div>
            </div>
          </details>
        </div>

        <div class="line-actions">
          <button class="row-btn" :disabled="idx === 0" title="上移" @click="moveUp(idx)">
            <Icon name="chevron-left" size="sm" />
          </button>
          <button class="row-btn" :disabled="idx === form.lines.length - 1" title="下移" @click="moveDown(idx)">
            <Icon name="chevron-right" size="sm" />
          </button>
          <button class="row-btn" title="复制" @click="duplicateLine(idx)">
            <Icon name="layers" size="sm" />
          </button>
          <button class="row-btn danger" title="删除" @click="removeLine(idx)">
            <Icon name="trash" size="sm" />
          </button>
        </div>
      </article>

      <div v-if="form.lines.length === 0" class="lines-empty" @click="addLine">
        <Icon name="plus" size="md" />
        <span>暂无台词，点击此处快速添加第一句</span>
      </div>
    </div>

    <!-- 底部控制 -->
    <div class="dialogue-footer">
      <button class="ghost-btn" @click="importConfig">
        <Icon name="upload" size="sm" />
        <span>载入本地样例剧本</span>
      </button>
      <button
        class="primary-btn"
        :disabled="form.lines.length === 0 || !modelStatus.base.ready"
        @click="submitDialogue"
      >
        <Icon name="dialogue" size="sm" />
        <span>一键合成多角色剧场配音</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useCapabilitiesStore } from '../stores/capabilities';
import { useSynthStore } from '../stores/synth';
import { useTasksStore } from '../stores/tasks';
import { useVoicesStore } from '../stores/voices';
import WarnBanner from '../components/WarnBanner.vue';
import Icon from '../components/Icon.vue';

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
      output_name: '',
    },
  ],
});

const personaOptions = computed(() =>
  Object.entries(personas.value || {}).map(([key, p]) => ({
    label: `${p.name} (${key})`,
    value: key,
  })),
);

const newLine = () => ({
  role: '',
  persona: '',
  text: '',
  tone: '',
  emotion: '',
  emotion_priority: false,
  output_name: '',
});

const addLine = () => form.lines.push(newLine());
const removeLine = (idx) => form.lines.splice(idx, 1);
const duplicateLine = (idx) => {
  form.lines.splice(idx + 1, 0, JSON.parse(JSON.stringify(form.lines[idx])));
};
const moveUp = (idx) => {
  if (idx === 0) return;
  const tmp = form.lines[idx];
  form.lines[idx] = form.lines[idx - 1];
  form.lines[idx - 1] = tmp;
};
const moveDown = (idx) => {
  if (idx === form.lines.length - 1) return;
  const tmp = form.lines[idx];
  form.lines[idx] = form.lines[idx + 1];
  form.lines[idx + 1] = tmp;
};

const importConfig = async () => {
  showLoading('正在载入本地样例剧本...');
  try {
    await loadDialogueSample();
    form.project_name = 'xingchi_reveal';
    form.title = '无厘头暗坊';
    form.emotion_priority = true;
    form.lines = [
      {
        role: 'demo_narrator',
        persona: 'demo_narrator',
        text: '名门讲道义，皇权讲法度，可这暗坊的影子里，只认『价值』。宁观尘想借孤山的剑，慕夕歌要窥天下的局。殊不知跨过这道槛，两人便已从看客，成了这死局里…… 最先祭旗的棋子。',
        tone: '无厘头、机灵、带点夸张反差喜感，节奏灵活。',
        emotion: '夸张、调侃、反差喜剧',
        emotion_priority: true,
        output_name: 'jianghu_anfang_1.wav',
      },
    ];
    showToast('本地样例剧本已载入', 'success');
  } catch {
    showToast('载入失败', 'error');
  } finally {
    hideLoading();
  }
};

const submitDialogue = async () => {
  if (form.lines.length === 0) return showToast('剧本中至少需要有一行台词', 'warning');
  for (let i = 0; i < form.lines.length; i++) {
    const line = form.lines[i];
    line.role = line.persona;
    if (!line.persona) return showToast(`第 ${i + 1} 行未选择配音角色`, 'warning');
    if (!line.text.trim()) return showToast(`第 ${i + 1} 行台词不能为空`, 'warning');
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
  max-width: 1080px;
  margin: 0 auto;
}

/* meta */
.meta-card {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-4);
}
.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--vf-space-4);
}
.meta-cell { display: flex; flex-direction: column; gap: 6px; }
.meta-label { font-size: 12px; color: var(--vf-text-2); }
.switch-row {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
  color: var(--vf-text-2);
  cursor: pointer;
  height: 34px;
}
.switch-tip { font-size: 11px; color: var(--vf-text-3); }

/* 台词行 */
.lines-head {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
}
.lines-title { font-size: 14px; font-weight: 600; color: var(--vf-text-1); }
.lines-count {
  font-size: 11px;
  color: var(--vf-text-3);
  background: var(--vf-bg-3);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
}
.add-line-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--vf-primary-soft);
  color: var(--vf-primary);
  border: 1px solid transparent;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.add-line-btn:hover {
  background: var(--vf-primary);
  color: white;
  transform: translateY(-1px);
}

.lines-list {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-3);
}
.line-card {
  display: flex;
  align-items: stretch;
  gap: var(--vf-space-3);
  padding: var(--vf-space-4);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  transition: border-color 0.15s;
}
.line-card:hover { border-color: var(--vf-border-strong); }
.line-index {
  background: var(--vf-bg-4);
  color: var(--vf-text-2);
  font-size: 12px;
  font-weight: 700;
  padding: 4px var(--vf-space-2);
  border-radius: var(--vf-radius-sm);
  align-self: flex-start;
  font-variant-numeric: tabular-nums;
  flex: none;
}
.line-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--vf-space-3); }
.line-grid {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: var(--vf-space-3);
}
.line-label { font-size: 11px; color: var(--vf-text-3); }
.line-persona, .line-text { display: flex; flex-direction: column; gap: 4px; }

.line-advanced {
  border-top: 1px dashed var(--vf-border);
  padding-top: var(--vf-space-3);
}
.line-advanced-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--vf-text-2);
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.line-advanced-head::-webkit-details-marker { display: none; }
.line-advanced-head .chevron {
  margin-left: auto;
  transition: transform 0.15s var(--vf-ease);
}
.line-advanced[open] .line-advanced-head .chevron { transform: rotate(180deg); }
.line-advanced-body {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: var(--vf-space-3);
  padding-top: var(--vf-space-3);
}
.form-cell { display: flex; flex-direction: column; gap: 4px; }

.line-actions {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-1);
  flex: none;
}
.row-btn {
  width: 28px;
  height: 28px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  border-radius: var(--vf-radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}
.row-btn:hover:not(:disabled) {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}
.row-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.row-btn.danger:hover { color: var(--vf-err); border-color: var(--vf-err); }

.lines-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--vf-space-2);
  border: 2px dashed var(--vf-border-strong);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-8);
  color: var(--vf-text-3);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.lines-empty:hover {
  border-color: var(--vf-primary);
  color: var(--vf-primary);
  background: var(--vf-primary-soft);
}

/* footer */
.dialogue-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: var(--vf-space-4);
  border-top: 1px solid var(--vf-border);
  gap: var(--vf-space-3);
  flex-wrap: wrap;
}
.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  padding: 7px 14px;
  border-radius: var(--vf-radius-sm);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.ghost-btn:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}
.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: white;
  border: 1px solid white;
  color: black;
  font-size: 13px;
  font-weight: 600;
  padding: 9px 18px;
  border-radius: var(--vf-radius-sm);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.primary-btn:hover:not(:disabled) {
  background: #e4e4e7;
  border-color: #e4e4e7;
  transform: translateY(-1px);
}
.primary-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

@media (max-width: 760px) {
  .meta-grid { grid-template-columns: 1fr; }
  .line-grid { grid-template-columns: 1fr; }
  .line-advanced-body { grid-template-columns: 1fr 1fr; }
}
</style>
