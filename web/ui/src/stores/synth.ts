/**
 * 克隆合成、音色设计、脚本与剧本任务状态。
 * API：/api/clone、/api/design、/api/scripts、/api/dialogue
 */
import { reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';
import { useTasksStore } from './tasks';

/** 克隆合成表单。 */
interface CloneForm {
  persona: string;
  text: string;
  tone: string;
  emotion: string;
  emotionPriority: boolean;
}

/** 音色设计表单。 */
interface DesignForm {
  name: string;
  text: string;
  tone: string;
  emotion: string;
  commit: boolean;
}

/** /api/personas 返回的 design presets 条目；契约里 presets 是 unknown[]，这里描述实际形状。 */
export interface DesignPreset {
  voice_name: string;
  tone: string;
  text: string;
  emotion: string;
}

/** 草稿箱条目（CloneTab 消费 id/title/content）。 */
interface SavedScript {
  id: string;
  title: string;
  content: string;
}

/** 克隆任务请求体。 */
interface CloneRequestBody {
  persona: string;
  text: string;
  tone: string;
  emotion: string;
  emotion_priority: boolean;
}

/** 音色设计任务请求体。 */
interface DesignRequestBody {
  voice_name: string;
  text: string;
  tone: string;
  emotion: string;
  commit: boolean;
}

/** 剧本任务请求体（DialogueTab 的 form）。 */
interface DialogueLine {
  role: string;
  persona: string;
  text: string;
  tone: string;
  emotion: string;
  emotion_priority: boolean;
  output_name: string;
}

interface DialogueForm {
  project_name: string;
  title: string;
  type: string;
  emotion_priority: boolean;
  lines: DialogueLine[];
}

const createCloneForm = (): CloneForm => ({ persona: '', text: '', tone: '', emotion: '', emotionPriority: false });
const createDesignForm = (): DesignForm => ({ name: '', text: '', tone: '', emotion: '', commit: false });

export const useSynthStore = defineStore('synth', () => {
  const cloneForm = reactive<CloneForm>(createCloneForm());
  const designForm = reactive<DesignForm>(createDesignForm());
  const designPresets = ref<DesignPreset[]>([]);
  const savedScripts = ref<SavedScript[]>([]);
  const error = ref('');

  const loadScripts = async (): Promise<SavedScript[]> => {
    error.value = '';
    try {
      const data = await api.scripts();
      savedScripts.value = (data.scripts || []) as SavedScript[];
      return savedScripts.value;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  const loadScript = (script: SavedScript) => {
    cloneForm.text = script.content || '';
  };

  const saveScript = async (text: string): Promise<{ ok: boolean; scripts: unknown[] }> => {
    error.value = '';
    try {
      // 后端 ScriptSaveRequest 要 {title, content}（title 可空，后端用 content
      // 前 20 字兜底）。之前这里引用不存在的 scriptText 变量、字段又发成 text
      // —— 请求体是 {text: undefined}，后端 422，而调用方没 await，成功 toast
      // 照弹，草稿其实从来没存上过。
      const data = await api.saveScript({ content: text });
      savedScripts.value = (data.scripts || []) as SavedScript[];
      return data;
    } catch (cause) {
      const vox = await useTasksStore().reportError(cause, { action: 'script.save' });
      error.value = vox.message;
      throw cause;
    }
  };

  const deleteScript = async (id: string): Promise<{ ok: boolean }> => {
    error.value = '';
    try {
      const data = await api.deleteScript(id);
      // api 层把 DELETE /api/scripts/{id} 的返回标成 { ok }，但原实现读了
      // data.scripts 刷新列表，这里按原实现的读取放宽类型。
      savedScripts.value = (data as { scripts?: SavedScript[] }).scripts || [];
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  const submitTask = async (
    url: string,
    body: unknown,
    loadingText: string,
  ): Promise<{ task_id: string }> => {
    const tasks = useTasksStore();
    error.value = '';
    tasks.showLoading(loadingText);
    try {
      // 参数名是 body —— 之前写成 payload（不存在的变量），克隆/设计/剧本
      // 任何一路点提交都是 ReferenceError，任务根本不会建，页面还没任何提示。
      const data = await (url.includes('design') ? api.design(body)
        : url.includes('dialogue') ? api.dialogue(body) : api.clone(body));
      tasks.taskPanelCollapsed = false;
      tasks.showToast('任务已提交，请在右下角任务队列中关注进度', 'success');
      return data;
    } catch (cause) {
      // 走标准错误入口：HTTP 上下文 + 堆栈都进错误日志，toast 8 秒可关
      const vox = await tasks.reportError(cause, {
        action: url.includes('design') ? 'synth.design' : url.includes('dialogue') ? 'synth.dialogue' : 'synth.clone',
        tags: { textLen: typeof (body as { text?: string })?.text === 'string' ? (body as { text: string }).text.length : 0 },
      });
      error.value = vox.message;
      throw cause;
    } finally {
      tasks.hideLoading();
    }
  };

  const doClone = (): Promise<{ task_id: string }> => submitTask('/api/clone', {
    persona: cloneForm.persona,
    text: cloneForm.text,
    tone: cloneForm.tone,
    emotion: cloneForm.emotion,
    emotion_priority: cloneForm.emotionPriority,
  }, '正在提交克隆合成任务...');

  const doDesign = (): Promise<{ task_id: string }> => submitTask('/api/design', {
    voice_name: designForm.name,
    text: designForm.text,
    tone: designForm.tone,
    emotion: designForm.emotion,
    commit: designForm.commit,
  }, '正在提交音色设计任务...');

  const loadDialogueSample = async (): Promise<{ scripts: unknown[] }> => {
    error.value = '';
    try {
      const data = await api.scripts();
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  const submitDialogue = (form: DialogueForm): Promise<{ task_id: string }> =>
    submitTask('/api/dialogue', form, '正在提交剧本合成任务...');

  return {
    cloneForm, designForm, designPresets, savedScripts, error,
    loadScripts, loadScript, saveScript, deleteScript, doClone, doDesign, loadDialogueSample, submitDialogue,
  };
});
