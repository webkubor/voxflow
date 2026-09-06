<template>
  <div class="tab-content-container">
    <section class="intake">
      <header class="intake-head">
        <h2>自动化发布</h2>
        <!-- 「歌是怎么来的」有两条路，此前界面上完全没体现 ——
             拿到音频的新人不知道自己该走哪条，只能挨个 tab 点过去。 -->
        <div class="paths">
          <div class="path">
            <span class="pn">A</span>
            <div>
              <b>别人给我一个链接</b>
              <p>台账里那条「⬇ 下载音频」，复制粘贴到下面即可。<br>
                 <b>不需要 Suno 账号，也不需要下 7GB 模型。</b></p>
            </div>
          </div>
          <div class="path">
            <span class="pn">B</span>
            <div>
              <b>歌是我自己在这台机器上生成的</b>
              <p>不用走这一页 —— 去「AI 音乐」生成，产物会自动进
                 <a href="#/works">发歌记录</a>。这里是给「只拿到音频」的人用的。</p>
            </div>
          </div>
        </div>
      </header>

      <!-- 选完平台第一件事是确认能不能发，不是先填表单。
           物料齐了也可能发不出去：没登录、museav 没积分、harness 没装。 -->
      <div v-if="pre" class="pre" :class="{ blocked: !pre.可以发布 }">
        <div class="pre-head">
          <b>{{ pre.可以发布 ? '这台机器可以发布' : '还发不了：' + pre.阻塞项.join('、') }}</b>
          <button class="ghost-btn small" @click="loadPre">重新检查</button>
        </div>
        <div v-for="i in pre.items" :key="i.项" class="pre-row" :class="{ bad: i.可自动验证 && !i.就绪 }">
          <span class="pre-mark">{{ i.就绪 ? '✓' : (i.可自动验证 ? '✗' : '?') }}</span>
          <span class="pre-name">{{ i.项 }}</span>
          <span class="pre-detail">{{ i.说明 }}</span>
          <a v-if="i.链接" :href="i.链接" target="_blank" rel="noopener" class="pre-link">去登录 →</a>
        </div>
      </div>

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
import { reactive, ref, onMounted, watch } from 'vue';
import { api } from '../api';
import { useTasksStore } from '../stores/tasks';

const tasksStore = useTasksStore();
const busy = ref(false);
const result = ref(null);
const platforms = ref({});
const pre = ref(null);

/** 前置条件。换平台就重查 —— 每个平台的登录和脚本都是独立的。 */
const loadPre = async () => {
  try { pre.value = await api.preflight(form.platform); }
  catch { pre.value = null; }
};

const form = reactive({
  url: '', title: '', album: '', platform: 'qishui',
  publisher: '', instrumental: true, with_cover: false,
});

onMounted(async () => {
  try {
    platforms.value = (await api.pipeline()).platforms || {};
    form.publisher = (await api.notifyOwner()).name || '';
  } catch { /* 拿不到就让人自己填，不拦流程 */ }
  loadPre();
});

watch(() => form.platform, loadPre);

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
.pre {
  margin-bottom: var(--vf-space-4); padding: 10px 12px; border-radius: 8px;
  border: 1px solid var(--vf-border, #333); font-size: 12.5px;
}
.pre.blocked { border-color: #ff7a5c; }
.pre-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.pre-row { display: flex; align-items: baseline; gap: 8px; padding: 2px 0; }
.pre-row.bad { color: #ff7a5c; }
.pre-mark { width: 12px; }
.pre-name { min-width: 9em; }
.pre-detail { color: var(--vf-text-3, #888); flex: 1; min-width: 0; }
.pre-link { flex: none; color: var(--vf-accent, #7c9cff); text-decoration: none; }

.paths { display: flex; flex-direction: column; gap: 10px; margin: 0 0 var(--vf-space-4); }
.path {
  display: flex; gap: 10px; padding: 10px 12px; border-radius: 8px;
  border: 1px solid var(--vf-border, #333); font-size: 13px; line-height: 1.7;
}
.path p { margin: 2px 0 0; color: var(--vf-text-3, #999); }
.pn {
  flex: none; width: 22px; height: 22px; border-radius: 50%;
  display: grid; place-items: center; font-size: 12px; font-weight: 600;
  background: var(--vf-bg-3, rgba(255,255,255,.08));
}

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
