<script setup>
/**
 * 改音色的名字和描述。
 *
 * 之所以只有这两个字段可改：key 是条目标识（别处引用它），
 * ref/design 是文件路径（该由上传和设计流程写），instruction 是合成时
 * 送给模型的基础指令（属于「怎么念」，不是「这是谁」）。
 * 名字和描述才是纯粹给人看的。
 */
import { ref, watch } from 'vue';
import { useVoicesStore } from '../stores/voices';

const props = defineProps({
  show: { type: Boolean, default: false },
  personaKey: { type: String, default: '' },
  persona: { type: Object, default: () => ({}) },
});
const emit = defineEmits(['update:show']);

const voicesStore = useVoicesStore();
const name = ref('');
const desc = ref('');
const saving = ref(false);
const err = ref('');

// 每次打开都从当前数据回填 —— 上次编辑留下的残值会让人以为改过了
watch(() => props.show, (open) => {
  if (!open) return;
  name.value = props.persona?.name || props.personaKey || '';
  desc.value = props.persona?.desc || '';
  err.value = '';
});

const close = () => emit('update:show', false);

const save = async () => {
  if (!name.value.trim()) { err.value = '名字不能为空'; return; }
  saving.value = true;
  err.value = '';
  try {
    await voicesStore.updatePersona(props.personaKey, {
      name: name.value.trim(),
      desc: desc.value,          // 不 trim 掉整体：允许存空串来清空描述
    });
    close();
  } catch (cause) {
    err.value = cause.message;   // 失败要留在弹窗里让人看见，不能静默关掉
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    title="编辑音色"
    style="max-width: 460px"
    @update:show="emit('update:show', $event)"
  >
    <n-form label-placement="top" @submit.prevent="save">
      <n-form-item label="名字">
        <n-input
          v-model:value="name"
          placeholder="想叫什么叫什么，中文、空格、标点都行"
          @keydown.enter.prevent="save"
        />
      </n-form-item>

      <n-form-item label="描述">
        <n-input
          v-model:value="desc"
          type="textarea"
          :rows="3"
          placeholder="音色特点、适合什么内容 —— 例如「低沉稳重，尾音干净，适合历史与人文题材」"
        />
      </n-form-item>

      <p class="hint">
        标识 <code>{{ personaKey }}</code> 不变，改名不影响已有音频。
      </p>

      <p v-if="err" class="err">{{ err }}</p>
    </n-form>

    <template #footer>
      <n-space justify="end">
        <n-button @click="close">取消</n-button>
        <n-button type="primary" :loading="saving" @click="save">保存</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<style scoped>
.hint {
  margin: 0;
  font-size: 12px;
  color: var(--vf-text-3);
}
.hint code {
  padding: 1px 5px;
  border-radius: var(--vf-radius-sm);
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
}
.err {
  margin: var(--vf-space-3) 0 0;
  font-size: 13px;
  color: var(--vf-err);
}
</style>
