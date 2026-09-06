<template>
  <div class="tab-content-container">
    <section class="intake">
      <header class="intake-head">
        <h2>贴链接 · 自动入库备料</h2>
        <p class="sub">
          从台账里复制「⬇ 下载音频」那个链接贴进来。
          自动下载 → 入库 → 备料，之后照着清单去平台上传就行。
          <b>不需要 Suno 账号，也不需要下载 AI 模型。</b>
        </p>
      </header>

      <div class="form">
        <label class="row">
          <span class="lb">音频链接</span>
          <input v-model="form.url" class="in" placeholder="https://music.webkubor.online/voxflow/xxx.wav" />
        </label>
        <label class="row">
          <span class="lb">发行歌名</span>
          <input v-model="form.title" class="in" placeholder="留空则用链接里的文件名" />
        </label>
        <label class="row">
          <span class="lb">归属专辑</span>
          <input v-model="form.album" class="in" placeholder="例如：破晓时分 · 纯音乐 BGM" />
        </label>
        <label class="row">
          <span class="lb">发布平台</span>
          <select v-model="form.platform" class="in">
            <option v-for="(p, k) in platforms" :key="k" :value="k">{{ p.label }}</option>
          </select>
        </label>
        <label class="row">
          <span class="lb">你的名字</span>
          <input v-model="form.publisher" class="in" placeholder="谁负责发这首（会记进发布记录）" />
        </label>

        <div class="row">
          <span class="lb">选项</span>
          <div class="opts">
            <label class="cb"><input v-model="form.instrumental" type="checkbox" /> 纯音乐（歌词自动标 [Instrumental]）</label>
            <!-- 出图花钱，必须显式勾。默认关不是保守，是不能替人花钱：
                 贴十个链接就是十块，而他可能只想先试一个。 -->
            <label class="cb warn">
              <input v-model="form.with_cover" type="checkbox" />
              顺便出封面（<b>每张约 ¥0.83</b>，走 museav）
            </label>
          </div>
        </div>

        <div class="row">
          <span class="lb"></span>
          <button class="primary-btn" :disabled="busy || !form.url.trim()" @click="submit">
            {{ busy ? '处理中…' : '导入并备料' }}
          </button>
        </div>
      </div>

      <div v-if="result" class="result" :class="{ bad: !result.ok }">
        <template v-if="result.ok">
          <div class="rline"><b>{{ result.title }}</b> 已入库 · {{ result['大小KB'] }} KB</div>
          <div v-if="result.封面" class="rline">
            封面：{{ result.封面.ok ? `已生成（扣 ${result.封面.credits} 积分）` : '失败 —— ' + result.封面.错误 }}
          </div>
          <div class="rline">
            备料：{{ result.备料.备料齐了 ? '✅ 齐了，可以去上传' : `还缺 ${result.备料.缺口数} 项` }}
          </div>
          <ul v-if="!result.备料.备料齐了" class="miss">
            <li v-for="m in result.备料.缺" :key="m">{{ m }}</li>
          </ul>
          <div v-if="result.备料.控制台" class="rline">
            <a :href="result.备料.控制台" target="_blank" rel="noopener">打开平台后台 →</a>
          </div>
          <div v-if="result.备料.发布命令" class="cmd" @click="copy(result.备料.发布命令)">
            {{ result.备料.发布命令 }}
            <span class="hint">点击复制 · 在项目目录执行会自动填表，最后一步提交由你点</span>
          </div>
        </template>
        <template v-else>{{ result.错误 }}</template>
      </div>
    </section>
  </div>
</template>

<script setup>
/**
 * 「自动化发布」入口 —— 给**只负责发布**的人用。
 *
 * 他们手里只有台账那条下载链接。此前要手动下载、改名、丢进目录、跑脚本，
 * 四步每步都能错（下到 Downloads 忘了移、名字对不上、路径记错）。
 * 这一页把四步收成一次粘贴。
 *
 * 刻意不放在「AI 音乐」里：那一屏要 Suno 会员和模型，而这类用户两样都没有，
 * 混在一起只会让他们以为自己用不了。
 */
import { reactive, ref, onMounted } from 'vue';
import { api } from '../api';
import { useTasksStore } from '../stores/tasks';

const tasksStore = useTasksStore();
const busy = ref(false);
const result = ref(null);
const platforms = ref({});

const form = reactive({
  url: '', title: '', album: '', platform: 'qishui',
  publisher: '', instrumental: true, with_cover: false,
});

onMounted(async () => {
  try {
    platforms.value = (await api.pipeline()).platforms || {};
    form.publisher = (await api.notifyOwner()).name || '';
  } catch { /* 拿不到就让人自己填，不拦流程 */ }
});

const submit = async () => {
  busy.value = true;
  result.value = null;
  try {
    result.value = await api.importUrl({ ...form, url: form.url.trim() });
  } catch (cause) {
    result.value = { ok: false, 错误: await tasksStore.toMessage?.(cause) || String(cause?.message || cause) };
    await tasksStore.reportError(cause, { action: 'pipeline.importUrl' });
  } finally {
    busy.value = false;
  }
};

const copy = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    tasksStore.showToast('命令已复制', 'success');
  } catch {
    tasksStore.showToast(text, 'info');
  }
};
</script>

<style scoped>
.intake { max-width: 720px; margin: 0 auto; padding: var(--vf-space-4) var(--vf-space-2); }
.intake-head h2 { margin: 0 0 6px; font-size: 18px; }
.sub { margin: 0 0 var(--vf-space-4); color: var(--vf-text-3, #999); font-size: 13px; line-height: 1.7; }
.form { display: flex; flex-direction: column; gap: 10px; }
.row { display: flex; align-items: center; gap: 12px; }
.lb { flex: none; width: 76px; font-size: 13px; color: var(--vf-text-3, #999); }
.in {
  flex: 1; min-width: 0; padding: 7px 10px; border-radius: 6px; font-size: 13px;
  border: 1px solid var(--vf-border, #333); background: transparent; color: inherit;
}
.opts { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.cb { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.cb.warn { color: #e8a33d; }
.result {
  margin-top: var(--vf-space-4); padding: 12px; border-radius: 8px; font-size: 13px;
  border: 1px solid var(--vf-border, #333); line-height: 1.8;
}
.result.bad { border-color: #ff7a5c; color: #ff7a5c; }
.rline { margin-bottom: 2px; }
.miss { margin: 4px 0 8px 18px; color: #ff7a5c; }
.cmd {
  margin-top: 8px; padding: 8px 10px; border-radius: 6px; cursor: pointer;
  background: var(--vf-bg-3, rgba(255,255,255,.05));
  font-family: ui-monospace, monospace; font-size: 12px; word-break: break-all;
}
.hint { display: block; margin-top: 4px; font-family: inherit; color: var(--vf-text-3, #888); }
</style>
