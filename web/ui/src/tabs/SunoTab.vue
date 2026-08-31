<template>
  <div class="tab-content-container">
    <!-- Suno 头部信息 -->
    <div class="suno-header-row">
      <h3 class="tab-title">AI 音乐 · Suno</h3>
      <div class="suno-auth-status">
        <n-tag v-if="suno.authenticated" type="success" size="small" round>
          ✅ {{ suno.plan || 'Suno' }} · {{ suno.total_credits_left }} credits
        </n-tag>
        <n-tag v-else type="warning" size="small" round>
          ⚠️ 未登录
        </n-tag>
        <n-button circle size="tiny" secondary @click="loadSunoStatus">
          🔄
        </n-button>
      </div>
    </div>

    <!-- 未登录提示条 -->
    <div v-if="!suno.authenticated" class="warn-banner">
      ⚠️ <strong>需要先登录 Suno</strong> — 在终端执行 <code>./voxsuno login</code>（自动从 Chrome 提取会话），然后点刷新。
    </div>

    <!-- 热点风向：哪个音乐火，做哪个风格（不抄袭） -->
    <div class="trend-card">
      <div class="trend-head">
        <span class="trend-title">📈 热点风向</span>
        <span class="trend-note">网易云热歌榜实时提炼 · 只学风格不抄作品</span>
        <n-button size="tiny" secondary :loading="trendLoading" @click="loadTrending">
          {{ trend ? '刷新' : '看当前火什么' }}
        </n-button>
      </div>

      <div v-if="trendError" class="trend-error">{{ trendError }}</div>

      <div v-else-if="trend" class="trend-body">
        <p class="trend-line">{{ trend.trend || '' }}</p>
        <div class="trend-tags">
          <n-tag
            v-for="tag in tagList"
            :key="tag"
            size="small"
            round
            :bordered="false"
            class="trend-tag"
            @click="applyTags(tag)"
            :title="'填入：' + tag"
          >
            {{ tag }}
          </n-tag>
          <n-button size="tiny" secondary @click="applyTags(trend.tags)">全部填入</n-button>
        </div>
        <div v-if="trend.moods?.length" class="trend-meta">
          情绪：{{ trend.moods.join(' / ') }}
        </div>
        <div v-if="trend.themes?.length" class="trend-meta">
          主题：{{ trend.themes.join(' / ') }}
        </div>
        <p class="trend-updated">更新于 {{ trendUpdated }} · 风格标签可点击填入左侧</p>
      </div>
    </div>

    <!-- 双栏表单布局 -->
    <div class="form-container">
      <n-grid :cols="2" :x-gap="20">
        <!-- 左侧参数 -->
        <n-grid-item>
          <n-form label-placement="top">
            <n-form-item label="🎵 歌曲标题">
              <n-input v-model:value="sunoForm.title" placeholder="例如：月下竹林" />
            </n-form-item>

            <n-form-item label="🎤 风格标签（逗号分隔）">
              <n-input v-model:value="sunoForm.tags" placeholder="古风, 古筝, 武侠, cinematic, 110 BPM" />
            </n-form-item>

            <n-form-item label="👤 声音 Persona">
              <n-select 
                v-model:value="sunoForm.persona" 
                :options="personaOptions" 
                placeholder="请选择 Suno 声音 Persona" 
              />
              <div class="persona-help-tip">
                需要先有 persona：<code>./voxsuno sample &lt;voxkey&gt;</code> 生成样音 → suno.com 上传建 voice → <code>./voxsuno link &lt;id&gt; &lt;名字&gt;</code>
              </div>
            </n-form-item>
          </n-form>
        </n-grid-item>

        <!-- 右侧歌词 -->
        <n-grid-item>
          <n-form label-placement="top">
            <n-form-item>
              <template #label>
                <div class="lyrics-label-row">
                  <span>📝 歌词（支持 [Verse] [Chorus] 结构）</span>
                  <n-space size="small">
                    <n-button size="tiny" secondary :loading="lyricsGenerating" @click="generateLyrics">
                      AI 生成
                    </n-button>
                    <n-button size="tiny" secondary :disabled="!sunoForm.lyrics.trim()" @click="copyLyrics">
                      复制歌词
                    </n-button>
                  </n-space>
                </div>
              </template>
              <n-input
                v-model:value="lyricsPrompt"
                placeholder="歌词主题（留空则根据标题和风格生成）"
                class="lyrics-prompt-input"
              />
              <n-input 
                v-model:value="sunoForm.lyrics" 
                type="textarea" 
                :rows="8" 
                class="lyrics-input"
                placeholder="[Verse 1]&#10;月下竹林深&#10;我踏碎霜痕&#10;&#10;[Chorus]&#10;月下竹林 我独行&#10;江湖夜雨十年灯"
              />
            </n-form-item>
          </n-form>
        </n-grid-item>
      </n-grid>

      <!-- 底部控制区 -->
      <div class="suno-footer-actions">
        <n-space align="center">
          <n-button 
            type="primary" 
            size="large"
            :loading="suno.submitting" 
            :disabled="suno.submitting || !suno.authenticated" 
            @click="submitSuno"
          >
            🎵 生成音乐
          </n-button>
          <span class="cost-tip">生成约耗 35-70 credits · 产物进「音频库」</span>
        </n-space>
        
        <p v-if="suno.error" class="suno-error-text">{{ suno.error }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * Suno AI 音乐创作选项卡
 * 职责：连接 Suno 后端授权状态，收集风格歌词参数，提交生成音乐并启动异步轮询
 * API 来源：GET /api/suno/status, POST /api/suno/generate
 */
import { computed, ref } from 'vue';
import copy from 'copy-to-clipboard';
import { api, toMessage } from '../api';
import { useSunoStore } from '../stores/suno';

const {
  suno, sunoForm, lyricsPrompt, lyricsGenerating,
  loadSunoStatus, submitSuno, generateLyrics,
} = useSunoStore();

// ── 热点风向（测试1：哪个音乐火做哪个风格，不抄袭）──
const trend = ref(null);
const trendError = ref('');
const trendLoading = ref(false);

const loadTrending = async () => {
  trendLoading.value = true;
  trendError.value = '';
  try {
    const data = await api.trending();
    if (!data.ok) {
      trendError.value = data.error || '热点获取失败';
    } else {
      trend.value = data.trend || null;
      trendUpdated.value = data.updated || '';
    }
  } catch (cause) {
    trendError.value = await toMessage(cause);
  } finally {
    trendLoading.value = false;
  }
};
const trendUpdated = ref('');

/** 标签串拆成单个标签（逗号/顿号分隔，去掉空白） */
const tagList = computed(() =>
  (trend.value?.tags || '').split(/[,，]/).map((s) => s.trim()).filter(Boolean),
);

const applyTags = (tags) => {
  const current = sunoForm.tags.trim();
  sunoForm.tags = current ? `${current}, ${tags}` : tags;
};

const copyLyrics = () => {
  const copied = copy(sunoForm.lyrics);
  window.$message?.[copied ? 'success' : 'error'](
    copied ? '歌词已复制，可直接粘贴到自动化流程' : '复制失败，请手动选择歌词复制',
  );
};

// 将 suno.personas 对象格式化为 Naive UI Select 组件所需的 options
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
  display: flex;
  flex-direction: column;
  height: 100%;
}

.suno-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

/* 热点风向卡 */
.trend-card {
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  background: var(--vf-bg-2);
  padding: 12px 16px;
  margin-bottom: 16px;
}
.trend-head {
  display: flex; align-items: center; gap: 10px;
}
.trend-title { font-weight: 600; color: var(--vf-text-1); font-size: 13px; }
.trend-note { font-size: 11px; color: var(--vf-text-3); margin-right: auto; }
.trend-error { margin-top: 8px; font-size: 12px; color: var(--vf-err, #b5564f); }
.trend-body { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
.trend-line { margin: 0; font-size: 13px; color: var(--vf-text-1); line-height: 1.6; }
.trend-tags { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.trend-tag { cursor: pointer; }
.trend-tag:hover { opacity: .8; }
.trend-meta { font-size: 12px; color: var(--vf-text-2); }
.trend-updated { margin: 0; font-size: 10px; color: var(--vf-text-3); }

.tab-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--vf-text-1);
}

.suno-auth-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.warn-banner {
  background-color: rgba(240, 160, 32, 0.1);
  border: 1px solid var(--vf-gold);
  border-radius: 6px;
  color: var(--vf-gold);
  padding: 10px 15px;
  font-size: 13px;
  margin-bottom: 16px;
}

.form-container {
  background-color: var(--vf-bg-1);
  border: 1px solid var(--vf-bg-4);
  border-radius: 8px;
  padding: 20px;
}

.persona-help-tip {
  font-size: 11px;
  color: var(--vf-text-3);
  margin-top: 6px;
  line-height: 1.4;
}

.lyrics-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vf-space-2);
  width: 100%;
}

.lyrics-prompt-input {
  margin-bottom: var(--vf-space-2);
}

.lyrics-input :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.cost-tip {
  font-size: 12px;
  color: var(--vf-text-3);
}

.suno-footer-actions {
  margin-top: 16px;
  border-top: 1px solid var(--vf-bg-4);
  padding-top: 16px;
}

.suno-error-text {
  color: var(--vf-err);
  font-size: 13px;
  margin-top: 8px;
  margin-bottom: 0;
}
</style>
