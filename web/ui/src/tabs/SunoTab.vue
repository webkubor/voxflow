<template>
  <div class="tab-content-container">
    <!-- 头部 -->
    <header class="suno-head">
      <h3 class="tab-title">
        <Icon name="suno" size="md" />
        <span>AI 音乐 · Suno</span>
      </h3>
      <div class="auth-status">
        <span v-if="suno.authenticated" class="credit-pill">
          ✅ {{ suno.plan || 'Suno' }} · {{ suno.total_credits_left }} credits
        </span>
        <span v-else class="credit-pill warn">⚠️ 未登录</span>
        <button class="icon-btn" title="刷新状态" @click="loadSunoStatus">
          <Icon name="refresh" size="sm" />
        </button>
      </div>
    </header>

    <WarnBanner
      v-if="!suno.authenticated"
      type="warn"
      title="需要先登录 Suno"
      hint="在终端执行 ./voxsuno login（自动从 Chrome 提取会话），然后点刷新。"
    />

    <!-- 三种模式切换 -->
    <div class="mode-switcher" role="tablist" aria-label="生成模式">
      <button
        v-for="m in MODES"
        :key="m.value"
        class="mode-btn"
        :class="{ active: mode === m.value }"
        role="tab"
        :aria-selected="mode === m.value"
        @click="mode = m.value"
      >
        <Icon :name="m.icon" size="sm" />
        <div class="mode-text">
          <span class="mode-label">{{ m.label }}</span>
          <span class="mode-desc">{{ m.desc }}</span>
        </div>
      </button>
    </div>

    <!-- 提示横幅：根据模式 -->
    <WarnBanner
      v-if="mode === 'bgm'"
      type="info"
      title="纯背景音乐模式"
      hint="将生成不含人声的纯音乐。系统会自动追加 instrumental 标签并发送 [Instrumental] 占位。"
    />
    <WarnBanner
      v-if="mode === 'cover'"
      type="success"
      title="翻唱热点歌曲"
      hint="选一首当前热歌 + 你的声音 Persona → 生成同曲不同演绎的版本。需要先把你的音色链接到 Suno：./voxsuno link &lt;suno_voice_id&gt; &lt;名字&gt;"
    />

    <!-- 热点风向：所有模式都显示，但 cover 模式下行为变 -->
    <section class="trend-card">
      <div class="trend-head">
        <Icon name="trend-up" size="sm" />
        <span class="trend-title">热点风向</span>
        <span class="trend-note">
          {{ mode === 'cover' ? '点击歌曲直接翻唱（带你的声音）' : '网易云热歌榜提炼 · 只学风格不抄作品' }}
        </span>
        <button class="ghost-btn" :disabled="trendLoading" @click="loadTrending">
          <Icon name="refresh" size="sm" />
          <span>{{ trend ? '刷新' : '看当前火什么' }}</span>
        </button>
      </div>

      <div v-if="trendError" class="trend-error">{{ trendError }}</div>

      <div v-else-if="trend" class="trend-body">
        <p class="trend-line">{{ trend.trend || '' }}</p>

        <div v-if="trend.hotness" class="hotness">
          <span class="hotness-n">值得做：{{ trend.hotness }}/10</span>
          <div class="hotness-bar">
            <div class="hotness-fill" :style="{ width: trend.hotness * 10 + '%' }"></div>
          </div>
          <span class="hotness-reason">{{ trend.hotness_reason }}</span>
        </div>

        <div class="trend-tags">
          <button
            v-for="tag in tagList"
            :key="tag"
            class="tag-chip"
            :title="`填入：${tag}`"
            @click="applyTags(tag)"
          >
            {{ tag }}
          </button>
          <button class="tag-chip outline" @click="applyTags(trend.tags)">
            <Icon name="arrow-right" size="sm" />
            <span>全部填入</span>
          </button>
        </div>

        <div v-if="trend.moods?.length" class="trend-meta">
          <span class="meta-k">情绪</span>
          <span>{{ trend.moods.join(' / ') }}</span>
        </div>
        <div v-if="trend.themes?.length" class="trend-meta">
          <span class="meta-k">主题</span>
          <span>{{ trend.themes.join(' / ') }}</span>
        </div>

        <div v-if="hotSongs.length" class="hot-chart">
          <div class="chart-title">🔥 当前热度榜 Top{{ hotSongs.length }}</div>
          <div v-for="s in hotSongs" :key="s.name" class="chart-row">
            <span class="chart-rank">{{ s.rank }}</span>
            <span class="chart-name">{{ s.name }}</span>
            <span class="chart-artist">{{ s.artist }}</span>
            <span v-if="s.platforms.length > 1" class="chart-both" title="网易云 + QQ 双榜上榜">双榜</span>
            <span class="chart-score">{{ s.score }}</span>
            <button
              v-if="mode === 'cover'"
              class="cover-pick-btn"
              :title="`用你的声音翻唱《${s.name}》`"
              @click="pickCoverSong(s)"
            >
              <Icon name="layers" size="sm" />
              <span>翻唱这首</span>
            </button>
          </div>
        </div>

        <div v-if="mode === 'song'" class="trend-actions">
          <button class="primary-btn" @click="useThemeForLyrics">
            <Icon name="sparkles" size="sm" />
            <span>用热点主题写歌词</span>
          </button>
          <span class="trend-updated">更新于 {{ trendUpdated }} · 只学风格不抄作品</span>
        </div>
      </div>
    </section>

    <!-- 表单 -->
    <section class="form-card">
      <!-- ─── SONG 模式：双栏 ─── -->
      <div v-if="mode === 'song'" class="form-grid">
        <div class="form-col">
          <div class="form-cell">
            <label class="form-label">🎵 歌曲标题</label>
            <n-input v-model:value="sunoForm.title" placeholder="如：月下竹林" />
          </div>

          <div class="form-cell">
            <label class="form-label">🎤 风格标签（逗号分隔）</label>
            <n-input
              v-model:value="sunoForm.tags"
              placeholder="古风, 古筝, 武侠, cinematic, 110 BPM"
            />
          </div>

          <div class="form-cell">
            <label class="form-label">👤 声音 Persona</label>
            <n-select
              v-model:value="sunoForm.persona"
              :options="personaOptions"
              placeholder="请选择 Suno 声音 Persona"
            />
            <p class="form-hint">
              需要先有 persona：<code>./voxsuno sample &lt;voxkey&gt;</code> 生成样音 → suno.com 上传建 voice → <code>./voxsuno link &lt;id&gt; &lt;名字&gt;</code>
            </p>
          </div>
        </div>

        <div class="form-col">
          <div class="form-cell">
            <div class="lyrics-head">
              <label class="form-label">📝 歌词（支持 [Verse] [Chorus] 结构）</label>
              <div class="lyrics-actions">
                <button
                  class="ghost-btn small"
                  :disabled="lyricsGenerating"
                  @click="generateLyrics"
                >
                  <Icon name="sparkles" size="sm" />
                  <span>{{ lyricsGenerating ? '生成中…' : 'AI 生成' }}</span>
                </button>
                <button
                  class="ghost-btn small"
                  :disabled="!sunoForm.lyrics.trim()"
                  @click="copyLyrics"
                >
                  <Icon name="layers" size="sm" />
                  <span>复制歌词</span>
                </button>
              </div>
            </div>
            <n-input
              v-model:value="lyricsPrompt"
              placeholder="歌词主题（留空则根据标题和风格生成）"
              class="mb-2"
            />
            <n-input
              v-model:value="sunoForm.lyrics"
              type="textarea"
              :rows="9"
              placeholder="[Verse 1]&#10;月下竹林深&#10;我踏碎霜痕&#10;&#10;[Chorus]&#10;月下竹林 我独行&#10;江湖夜雨十年灯"
            />
          </div>
        </div>
      </div>

      <!-- ─── BGM 模式：单栏 + 场景预设 ─── -->
      <div v-else-if="mode === 'bgm'" class="bgm-form">
        <div class="form-cell">
          <label class="form-label">🎵 标题（可选）</label>
          <n-input v-model:value="sunoForm.title" placeholder="留空则用 'Untitled BGM'" />
        </div>

        <div class="form-cell">
          <label class="form-label">🎼 风格标签（必填，自动追加 instrumental）</label>
          <n-input
            v-model:value="sunoForm.tags"
            placeholder="lo-fi, study, calm piano, ambient, 80 BPM"
          />
          <div class="bgm-presets">
            <span class="bgm-presets-label">一键场景：</span>
            <button
              v-for="p in BGM_PRESETS"
              :key="p.label"
              class="bgm-preset-chip"
              :title="p.tags"
              @click="applyBGMPreset(p)"
            >
              {{ p.label }}
            </button>
          </div>
        </div>

        <div class="bgm-note">
          <Icon name="info" size="sm" />
          <span>本首将作为纯背景音乐生成，不含人声。系统会自动加上 <code>instrumental</code> 标签。</span>
        </div>
      </div>

      <!-- ─── COVER 模式：原曲 + 你的声音 ─── -->
      <div v-else class="cover-form">
        <div class="cover-song-bar">
          <div class="cover-song-bar-text">
            <Icon name="layers" size="sm" />
            <span>当前翻唱：</span>
            <strong v-if="coverSong">{{ coverSong.name }} - {{ coverSong.artist }}</strong>
            <span v-else class="cover-song-empty">从上方热点榜选一首，或手动填原曲名</span>
          </div>
        </div>

        <div class="form-grid">
          <div class="form-col">
            <div class="form-cell">
              <label class="form-label">🎤 原曲（必填）</label>
              <n-input
                v-model:value="originalSong"
                placeholder="如：起风了"
              />
            </div>

            <div class="form-cell">
              <label class="form-label">🎵 翻唱标题（自动：原曲名 + Cover）</label>
              <n-input v-model:value="sunoForm.title" placeholder="如：起风了 (Cover)" />
            </div>

            <div class="form-cell">
              <label class="form-label">🎼 风格标签</label>
              <n-input
                v-model:value="sunoForm.tags"
                placeholder="已自动套用热点 tags，可调整"
              />
            </div>

            <!-- Persona 在 cover 模式下提到主位 -->
            <div class="form-cell persona-highlight">
              <div class="persona-label-row">
                <label class="form-label">🎙️ 用你的声音翻唱</label>
                <span v-if="suno.personas && Object.keys(suno.personas).length > 0" class="persona-available">
                  ✓ 已链接 {{ Object.keys(suno.personas).length }} 个
                </span>
                <span v-else class="persona-warning">⚠️ 未链接任何 Suno 声音</span>
              </div>
              <n-select
                v-model:value="sunoForm.persona"
                :options="personaOptions"
                placeholder="选择你之前设计并链接到 Suno 的声音"
                :disabled="!suno.personas || Object.keys(suno.personas).length === 0"
              />
              <p class="form-hint">
                没有现成的？先到「音色设计」合成一个，<code>./voxsuno sample</code> 生成样音 → suno.com 上传 → <code>./voxsuno link</code>
              </p>
            </div>
          </div>

          <div class="form-col">
            <div class="form-cell">
              <div class="lyrics-head">
                <label class="form-label">📝 歌词</label>
                <div class="lyrics-actions">
                  <button
                    class="ghost-btn small"
                    :disabled="lyricsGenerating"
                    @click="generateCoverLyrics"
                  >
                    <Icon name="sparkles" size="sm" />
                    <span>{{ lyricsGenerating ? '生成中…' : 'AI 改写' }}</span>
                  </button>
                  <button
                    class="ghost-btn small"
                    :disabled="!sunoForm.lyrics.trim()"
                    @click="copyLyrics"
                  >
                    <Icon name="layers" size="sm" />
                    <span>复制</span>
                  </button>
                </div>
              </div>
              <n-input
                v-model:value="lyricsPrompt"
                :placeholder="`翻唱《${originalSong || '原曲'}》的歌词主题`"
                class="mb-2"
              />
              <n-input
                v-model:value="sunoForm.lyrics"
                type="textarea"
                :rows="9"
                placeholder="粘贴原曲歌词，或让 AI 基于主题重新写一份。同曲不同词也行 —— 翻唱的核心是「你的演绎」。"
              />
            </div>
          </div>
        </div>
      </div>

      <div class="form-footer">
        <button
          class="primary-btn"
          :loading="suno.submitting"
          :disabled="submitDisabled"
          @click="handleSubmit"
        >
          <Icon :name="mode === 'bgm' ? 'library' : mode === 'cover' ? 'layers' : 'suno'" size="sm" />
          <span>{{ SUBMIT_LABELS[mode] }}</span>
        </button>
        <span class="cost-tip">{{ COST_TIPS[mode] }} · 产物进「资产库」</span>
      </div>
      <p v-if="suno.error" class="suno-error">{{ suno.error }}</p>
    </section>
  </div>
</template>

<script setup>
/**
 * Suno 音乐生成 - 三种模式：
 *
 *   歌曲 (song)  —— 完整原创歌曲：标题 + 风格 + 歌词 + 声音
 *   BGM (bgm)    —— 纯背景音乐：风格为主，自动追加 instrumental
 *   翻唱 (cover) —— 用**自己的声音**翻唱热歌：原曲 + 自己的 persona
 *
 * ## 为什么是三种模式
 *
 * Suno API 是一样的（/api/suno/generate），但用户意图不同：
 *
 * - 歌曲：希望有完整歌词和人声
 * - BGM：希望没有歌词（视频/学习/工作背景音）
 * - 翻唱：希望用某个已有曲子的旋律 + 自己的声音
 *
 * 不同意图下字段组合完全不同。混在一个表单里用户会困惑「这个歌词框要不要填？」
 * 「Persona 是干嘛的」—— 模式分清楚后，每个表单只问该问的问题。
 */
import { computed, ref } from 'vue';
import { storeToRefs } from 'pinia';
import copy from 'copy-to-clipboard';
import { api, toMessage } from '../api';
import { useSunoStore } from '../stores/suno';
import { useTasksStore } from '../stores/tasks';
import WarnBanner from '../components/WarnBanner.vue';
import Icon from '../components/Icon.vue';

const sunoStore = useSunoStore();
const tasksStore = useTasksStore();
const { suno, sunoForm } = sunoStore;
const { lyricsPrompt, lyricsGenerating } = storeToRefs(sunoStore);
const { loadSunoStatus, submitSuno, generateLyrics } = sunoStore;

// ─── 模式 ───
const MODES = [
  { value: 'song',  label: '歌曲',  desc: '完整原创',  icon: 'suno' },
  { value: 'bgm',   label: 'BGM',   desc: '纯背景音',  icon: 'library' },
  { value: 'cover', label: '翻唱',  desc: '你的声音',  icon: 'layers' },
];
const mode = ref('song');

// ─── BGM 场景预设 ───
const BGM_PRESETS = [
  { label: '📚 专注学习', tags: 'lo-fi, study, calm piano, ambient, 80 BPM' },
  { label: '☕ 咖啡时光', tags: 'jazz, lo-fi, cozy, vinyl crackle, 90 BPM' },
  { label: '🌙 助眠冥想', tags: 'ambient, drone, meditation, peaceful, 60 BPM' },
  { label: '💪 运动健身', tags: 'electronic, energetic, bass-heavy, 130 BPM' },
  { label: '🎬 影视史诗', tags: 'orchestral, cinematic, epic, trailer, 100 BPM' },
  { label: '📱 短视频',   tags: 'minimal, atmospheric, background, trendy, 120 BPM' },
];

// ─── 翻唱 ───
const originalSong = ref('');
const coverSong = ref(null);     // 当前从热点榜选的歌曲对象

const pickCoverSong = (song) => {
  coverSong.value = song;
  originalSong.value = song.name;
  sunoForm.title = `${song.name} (Cover)`;
  // 自动套用热点 tags
  if (trend.value?.tags) {
    sunoForm.tags = trend.value.tags;
  }
  // 主题喂给歌词 prompt
  const themes = trend.value?.themes?.length
    ? trend.value.themes.join(' / ')
    : song.name;
  lyricsPrompt.value = `翻唱《${song.name}》, 主题：${themes}`;
  tasksStore.showToast(`已选《${song.name}》,风格已自动套用热点 tags`, 'success');
};

const generateCoverLyrics = async () => {
  if (!originalSong.value.trim()) {
    tasksStore.showToast('先填写原曲名', 'warning');
    return;
  }
  // 复用 store 的 generateLyrics，但 prompt 里强调是翻唱改写
  const originalPrompt = lyricsPrompt.value;
  const hint = `翻唱《${originalSong.value}》`;
  lyricsPrompt.value = lyricsPrompt.value?.trim()
    ? `${hint}, 主题：${lyricsPrompt.value}`
    : hint;
  try {
    await generateLyrics();
  } finally {
    lyricsPrompt.value = originalPrompt;
  }
};

// ─── 提交按钮 ───
const SUBMIT_LABELS = {
  song: '生成音乐',
  bgm: '生成 BGM',
  cover: '生成翻唱',
};
const COST_TIPS = {
  song: '生成约耗 35-70 credits',
  bgm: '纯音乐约耗 25-50 credits',
  cover: '翻唱约耗 50-100 credits',
};

const submitDisabled = computed(() => {
  if (suno.submitting || !suno.authenticated) return true;
  if (mode.value === 'cover' && !originalSong.value.trim()) return true;
  if (mode.value === 'cover' && !sunoForm.persona) return true;
  return false;
});

const handleSubmit = async () => {
  try {
    if (mode.value === 'bgm') {
      // BGM：不带 persona / 歌词，强制 instrumental tag
      const trimmedTags = sunoForm.tags.trim();
      const hasInstr = /instrumental/i.test(trimmedTags);
      const tags = trimmedTags
        ? (hasInstr ? trimmedTags : `${trimmedTags}, instrumental`)
        : 'instrumental';
      await submitSuno({
        title: sunoForm.title.trim() || 'Untitled BGM',
        tags,
        lyrics: '[Instrumental]',
        persona: '',
      });
    } else if (mode.value === 'cover') {
      // 翻唱：原曲名作为上下文塞到 tags，persona 用用户选的
      const tagsWithCover = sunoForm.tags.trim()
        ? `${sunoForm.tags.trim()}, cover of ${originalSong.value}`
        : `cover of ${originalSong.value}`;
      await submitSuno({
        title: sunoForm.title.trim() || `${originalSong.value} (Cover)`,
        tags: tagsWithCover,
        lyrics: sunoForm.lyrics || `[Verse]\n${originalSong.value}（待填歌词）\n\n[Chorus]\n你的翻唱演绎`,
        persona: sunoForm.persona,
      });
    } else {
      // 歌曲：完全透传表单
      await submitSuno();
    }
  } catch (cause) {
    await tasksStore.reportError(cause, { action: `suno.${mode.value}.submit` });
  }
};

// ─── 热点风向 ───
const trend = ref(null);
const trendError = ref('');
const trendLoading = ref(false);
const trendUpdated = ref('');
const hotSongs = ref([]);

const loadTrending = async () => {
  trendLoading.value = true;
  trendError.value = '';
  try {
    const data = await api.trending();
    if (!data.ok) {
      trendError.value = data.error || '热点获取失败';
    } else {
      trend.value = data.trend || null;
      hotSongs.value = (data.songs || []).slice(0, 5);
      trendUpdated.value = data.updated || '';
    }
  } catch (cause) {
    trendError.value = await toMessage(cause);
  } finally {
    trendLoading.value = false;
  }
};

const tagList = computed(() =>
  (trend.value?.tags || '').split(/[,，]/).map((s) => s.trim()).filter(Boolean),
);

const applyTags = (tags) => {
  const current = sunoForm.tags.trim();
  sunoForm.tags = current ? `${current}, ${tags}` : tags;
};

const useThemeForLyrics = () => {
  const themes = trend.value?.themes || [];
  const theme = themes.length
    ? themes.slice(0, 2).join('、')
    : (trend.value?.trend || '');
  if (!theme) {
    window.$message?.warning?.('还没有热点主题，先点「看当前火什么」');
    return;
  }
  lyricsPrompt.value = theme + '，写一首全新原创的歌';
  generateLyrics();
};

const copyLyrics = () => {
  const copied = copy(sunoForm.lyrics);
  window.$message?.[copied ? 'success' : 'error'](
    copied ? '歌词已复制，可直接粘贴到自动化流程' : '复制失败，请手动选择歌词复制',
  );
};

const applyBGMPreset = (preset) => {
  sunoForm.tags = preset.tags;
  if (!sunoForm.title.trim()) sunoForm.title = preset.label.replace(/^[^ ]+ /, '');
  tasksStore.showToast(`已套用 ${preset.label}`, 'success');
};

const personaOptions = computed(() => {
  const options = [{ label: '（默认 Suno 声音）', value: '' }];
  if (suno.personas) {
    Object.entries(suno.personas).forEach(([name, id]) => {
      options.push({ label: `${name}`, value: name });
    });
  }
  return options;
});
</script>

<style scoped>
.tab-content-container {
  max-width: 1080px;
  margin: 0 auto;
}

.tab-title {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
}

/* ─── 头部 ─── */
.suno-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.auth-status { display: flex; align-items: center; gap: var(--vf-space-2); }
.credit-pill {
  font-size: 12px;
  background: var(--vf-ok-soft);
  color: var(--vf-ok);
  padding: 4px var(--vf-space-3);
  border-radius: var(--vf-radius-full);
}
.credit-pill.warn { background: var(--vf-warn-soft); color: var(--vf-warn); }
.icon-btn {
  width: 28px; height: 28px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  border-radius: var(--vf-radius-sm);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}
.icon-btn:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}

/* ─── 模式切换器 ─── */
.mode-switcher {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--vf-space-2);
  background: var(--vf-bg-1);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: 6px;
}
.mode-btn {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding: 10px 14px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--vf-radius-sm);
  color: var(--vf-text-2);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
  text-align: left;
}
.mode-btn:hover {
  color: var(--vf-text-1);
  background: var(--vf-bg-hover);
}
.mode-btn.active {
  background: var(--vf-primary-soft);
  border-color: var(--vf-primary);
  color: var(--vf-text-1);
}
.mode-btn.active .vf-icon { color: var(--vf-primary); }
.mode-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.mode-label {
  font-size: 13px;
  font-weight: 600;
}
.mode-desc {
  font-size: 11px;
  color: var(--vf-text-3);
}

/* ─── 热点风向 ─── */
.trend-card {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-3);
}
.trend-head {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  color: var(--vf-text-2);
}
.trend-title { font-weight: 600; color: var(--vf-text-1); font-size: 13px; }
.trend-note { font-size: 11px; color: var(--vf-text-3); margin-right: auto; }
.trend-error { font-size: 12px; color: var(--vf-err); }
.trend-body { display: flex; flex-direction: column; gap: var(--vf-space-2); }
.trend-line {
  margin: 0;
  font-size: 13px;
  color: var(--vf-text-1);
  line-height: 1.6;
}

.hotness { display: flex; align-items: center; gap: var(--vf-space-3); flex-wrap: wrap; }
.hotness-n { font-size: 12px; font-weight: 600; color: var(--vf-primary); }
.hotness-bar {
  width: 120px; height: 6px; border-radius: var(--vf-radius-full);
  background: var(--vf-bg-3); overflow: hidden;
}
.hotness-fill {
  display: block; height: 100%;
  background: linear-gradient(90deg, var(--vf-primary), var(--vf-primary-hover));
  border-radius: var(--vf-radius-full);
  transition: width 0.3s var(--vf-ease);
}
.hotness-reason { font-size: 11px; color: var(--vf-text-2); flex: 1; min-width: 200px; }

.trend-tags { display: flex; flex-wrap: wrap; align-items: center; gap: var(--vf-space-2); }
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--vf-primary-soft);
  border: 1px solid transparent;
  color: var(--vf-primary);
  font-size: 12px;
  padding: 3px 10px;
  border-radius: var(--vf-radius-full);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.tag-chip:hover {
  background: var(--vf-primary);
  color: white;
}
.tag-chip.outline {
  background: transparent;
  border-color: var(--vf-border-strong);
  color: var(--vf-text-2);
}
.tag-chip.outline:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-primary);
}

.trend-meta {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
  color: var(--vf-text-2);
}
.meta-k {
  font-size: 11px;
  color: var(--vf-text-3);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.hot-chart {
  border-top: 1px dashed var(--vf-border);
  padding-top: var(--vf-space-3);
}
.chart-title { font-size: 11px; color: var(--vf-text-3); margin-bottom: var(--vf-space-2); }
.chart-row {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
  padding: 3px 0;
}
.chart-rank {
  width: 18px;
  color: var(--vf-text-3);
  font-variant-numeric: tabular-nums;
}
.chart-name {
  color: var(--vf-text-1);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 200px;
}
.chart-artist {
  color: var(--vf-text-3);
  font-size: 11px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 160px;
}
.chart-both {
  font-size: 10px;
  color: #ff8a50;
  border: 1px solid #ff8a50;
  border-radius: var(--vf-radius-full);
  padding: 0 6px;
  flex: none;
}
.chart-score {
  margin-left: auto;
  color: var(--vf-text-2);
  font-variant-numeric: tabular-nums;
}
.cover-pick-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: var(--vf-primary);
  background: var(--vf-primary-soft);
  border: 1px solid transparent;
  padding: 2px 8px;
  border-radius: var(--vf-radius-full);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
  margin-left: var(--vf-space-2);
  flex: none;
}
.cover-pick-btn:hover {
  background: var(--vf-primary);
  color: white;
}

.trend-actions {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  flex-wrap: wrap;
}
.trend-updated { font-size: 11px; color: var(--vf-text-3); }

/* ─── 表单 ─── */
.form-card {
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--vf-space-5);
}
.form-col {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
}
.form-cell { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 12px; color: var(--vf-text-2); font-weight: 500; }
.form-hint {
  font-size: 11px;
  color: var(--vf-text-3);
  margin-top: 4px;
  line-height: 1.5;
}
.form-hint code {
  padding: 1px 5px;
  border-radius: var(--vf-radius-xs);
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
  font-size: 10px;
}

.lyrics-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vf-space-2);
  margin-bottom: var(--vf-space-2);
}
.lyrics-actions { display: flex; gap: var(--vf-space-2); }

.mb-2 { margin-bottom: var(--vf-space-2); }

/* ─── BGM 专属 ─── */
.bgm-form {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
}
.bgm-presets {
  display: flex;
  flex-wrap: wrap;
  gap: var(--vf-space-2);
  margin-top: var(--vf-space-2);
  align-items: center;
}
.bgm-presets-label {
  font-size: 11px;
  color: var(--vf-text-3);
  margin-right: var(--vf-space-2);
}
.bgm-preset-chip {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: var(--vf-radius-full);
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.bgm-preset-chip:hover {
  background: var(--vf-primary-soft);
  border-color: var(--vf-primary);
  color: var(--vf-primary);
}

.bgm-note {
  display: flex;
  align-items: flex-start;
  gap: var(--vf-space-2);
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  padding: var(--vf-space-3);
  font-size: 12px;
  color: var(--vf-text-2);
}
.bgm-note .vf-icon { color: var(--vf-primary); margin-top: 2px; }
.bgm-note code {
  padding: 1px 5px;
  border-radius: var(--vf-radius-xs);
  background: var(--vf-bg-2);
  color: var(--vf-text-1);
  font-size: 11px;
}

/* ─── Cover 专属 ─── */
.cover-form {
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-4);
}
.cover-song-bar {
  display: flex;
  align-items: center;
  padding: var(--vf-space-3) var(--vf-space-4);
  background: var(--vf-primary-soft);
  border: 1px solid var(--vf-primary);
  border-radius: var(--vf-radius-md);
}
.cover-song-bar-text {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 13px;
  color: var(--vf-primary);
}
.cover-song-bar strong {
  color: var(--vf-text-1);
  font-weight: 600;
}
.cover-song-empty {
  color: var(--vf-text-3);
  font-style: italic;
}

.persona-highlight {
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  padding: var(--vf-space-3) var(--vf-space-4);
  margin: calc(var(--vf-space-2) * -1) 0;
}
.persona-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vf-space-2);
  margin-bottom: 6px;
}
.persona-available {
  font-size: 10px;
  color: var(--vf-ok);
  background: var(--vf-ok-soft);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
}
.persona-warning {
  font-size: 10px;
  color: var(--vf-warn);
  background: var(--vf-warn-soft);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
}

/* ─── 共享 ─── */
.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  color: var(--vf-text-2);
  padding: 5px 12px;
  border-radius: var(--vf-radius-sm);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.ghost-btn:hover:not(:disabled) {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}
.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.ghost-btn.small { padding: 4px 10px; font-size: 11px; }

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: white;
  border: 1px solid white;
  color: black;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 18px;
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

.form-footer {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  padding-top: var(--vf-space-4);
  border-top: 1px solid var(--vf-border);
  flex-wrap: wrap;
}
.cost-tip { font-size: 12px; color: var(--vf-text-3); }
.suno-error { margin: 0; font-size: 13px; color: var(--vf-err); }

@media (max-width: 760px) {
  .form-grid { grid-template-columns: 1fr; }
  .mode-switcher { grid-template-columns: 1fr; }
  .mode-text { flex: 1; }
}
</style>
