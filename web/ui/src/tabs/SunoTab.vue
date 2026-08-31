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

    <!-- 热点风向 -->
    <section class="trend-card">
      <div class="trend-head">
        <Icon name="trend-up" size="sm" />
        <span class="trend-title">热点风向</span>
        <span class="trend-note">网易云热歌榜实时提炼 · 只学风格不抄作品</span>
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
          </div>
        </div>

        <div class="trend-actions">
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
      <div class="form-grid">
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

      <div class="form-footer">
        <button
          class="primary-btn"
          :loading="suno.submitting"
          :disabled="suno.submitting || !suno.authenticated"
          @click="submitSuno"
        >
          <Icon name="suno" size="sm" />
          <span>生成音乐</span>
        </button>
        <span class="cost-tip">生成约耗 35-70 credits · 产物进「资产库」</span>
      </div>
      <p v-if="suno.error" class="suno-error">{{ suno.error }}</p>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { storeToRefs } from 'pinia';
import copy from 'copy-to-clipboard';
import { api, toMessage } from '../api';
import { useSunoStore } from '../stores/suno';
import WarnBanner from '../components/WarnBanner.vue';
import Icon from '../components/Icon.vue';

const sunoStore = useSunoStore();
const { suno, sunoForm } = sunoStore;
const { lyricsPrompt, lyricsGenerating } = storeToRefs(sunoStore);
const { loadSunoStatus, submitSuno, generateLyrics } = sunoStore;

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

/* 头部 */
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

/* 热点风向 */
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

.trend-actions {
  display: flex;
  align-items: center;
  gap: var(--vf-space-3);
  flex-wrap: wrap;
}
.trend-updated { font-size: 11px; color: var(--vf-text-3); }

/* 表单 */
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
.form-label { font-size: 12px; color: var(--vf-text-2); }
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

/* action buttons */
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
}
</style>
