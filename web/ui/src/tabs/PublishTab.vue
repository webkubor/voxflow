<template>
  <div class="tab-content-container">
    <div class="publish-header">
      <div>
        <h3 class="tab-title">音乐自动发布</h3>
        <p class="tab-subtitle">账号登录、歌手身份与平台曲目发布台账</p>
      </div>
      <n-button secondary size="small" :loading="loading" @click="loadBoard">刷新状态</n-button>
    </div>

    <!-- 🎙️ 歌手身份与平台歌手 ID 绑定 (用户核心诉求，防止自动发布填错 ID) -->
    <n-card v-if="artist" size="small" class="artist-identity-card">
      <template #header>
        <div class="identity-header-title">
          <span>🎙️ 歌手身份与平台绑定</span>
          <span class="identity-header-sub">发布校验的唯一真源</span>
        </div>
      </template>
      <template #header-extra>
        <n-button size="tiny" secondary type="primary" @click="openEditArtistModal">
          ✎ 编辑歌手档案
        </n-button>
      </template>

      <div class="identity-layout">
        <!-- 基础身份信息 -->
        <div class="identity-info-box">
          <div class="info-item">
            <span class="info-label">公开艺名/歌手：</span>
            <span class="info-value-highlight">{{ artist.stage_name || '未登记' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">版权真实姓名：</span>
            <span class="info-value">{{ artist.real_name || '未登记' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">默认版权比例：</span>
            <span class="info-value-auth">{{ artist.defaults?.authorization_ratio || '100%' }} (词/曲/录音全自研)</span>
          </div>
        </div>

        <!-- 各平台歌手 ID 绑定状态 -->
        <div class="platform-profiles-box">
          <div class="profile-title">平台发布歌手 ID (自动读取)</div>
          <div class="profile-grid">
            <div 
              v-for="profile in artist.platform_profiles" 
              :key="profile.platform" 
              class="profile-item"
            >
              <span class="platform-dot"></span>
              <span class="platform-name">{{ profile.platform }}：</span>
              <span class="profile-id-badge">ID: {{ parseArtistId(profile.url) }}</span>
              <a :href="profile.url" target="_blank" class="profile-link-btn">
                歌手主页 ↗
              </a>
            </div>
            <div v-if="!artist.platform_profiles || artist.platform_profiles.length === 0" class="no-profiles-tip">
              ⚠️ 暂无绑定的歌手主页，请立即编辑以导入歌手 ID，防止自动化发布时填错！
            </div>
          </div>
        </div>
      </div>
    </n-card>

    <!-- 流水线在前、平台账号在后：先看歌走到哪、决定发不发，才轮到关心发去哪个账号。 -->
    <PipelineBoard />

    <n-alert type="warning" :show-icon="false" class="truth-alert">
      未接入的平台登录检测或云备份不会被伪装成成功；请在台账记录实际状态后再以此页为准。
    </n-alert>

    <!-- 平台发布状态卡片网格 -->
    <n-grid :cols="1" :m-cols="3" :x-gap="16" :y-gap="16" class="accounts-grid">
      <n-grid-item v-for="account in publishAccounts" :key="account.id">
        <n-card size="small" class="account-card">
          <template #header>
            <div class="account-heading">
              <span class="account-label-text">{{ account.label }}</span>
              <n-tag size="small" :type="loginTagType(account.login.status)" round>
                {{ account.login.label }}
              </n-tag>
            </div>
          </template>
          
          <!-- 平台登录详情 -->
          <p class="account-detail">{{ account.login.detail }}</p>
          
          <!-- 已发布歌曲及 ID 列表 -->
          <div class="release-heading">已记录曲目 · {{ account.releases.length }} 首</div>
          <n-space v-if="account.releases.length" vertical size="small" class="releases-list">
            <div v-for="release in account.releases" :key="release.id" class="release-row">
              <div class="release-left-meta">
                <span class="release-title" :title="release.title">{{ release.title }}</span>
                <!-- 展示可能存在的平台歌曲 ID (通过 url 或者 note 解析) -->
                <span v-if="getSongId(release)" class="song-id-tag">
                  ID: {{ getSongId(release) }}
                </span>
              </div>
              <n-space size="small" align="center">
                <n-tag size="tiny" :type="publishTagType(release.status)" round>{{ release.status }}</n-tag>
                <a 
                  v-if="getSongUrl(release)" 
                  :href="getSongUrl(release)" 
                  target="_blank" 
                  class="song-link-icon"
                  title="前往平台播放"
                >
                  🎵
                </a>
              </n-space>
            </div>
          </n-space>
          <n-empty v-else size="small" description="暂无已记录发布曲目" class="empty-releases" />
        </n-card>
      </n-grid-item>
    </n-grid>

    <n-card size="small" class="backup-card" title="所有歌曲的云备份">
      <n-list v-if="backupTracks.length" bordered>
        <n-list-item v-for="track in backupTracks" :key="track.id">
          <n-thing :title="track.title">
            <template #description>{{ track.cloud_backup.location || '尚未登记云端位置' }}</template>
            <template #header-extra>
              <n-tag size="small" :type="backupTagType(track.cloud_backup.status)">
                {{ track.cloud_backup.label }}
              </n-tag>
            </template>
          </n-thing>
        </n-list-item>
      </n-list>
      <n-empty v-else description="流水线中还没有歌曲记录" />
    </n-card>

    <p v-if="error" class="publish-error">{{ error }}</p>

    <!-- 🎙️ 歌手档案编辑弹窗 -->
    <n-modal
      v-model:show="showEditArtist"
      preset="card"
      style="width: 500px;"
      title="✎ 修改歌手身份与平台绑定"
      size="small"
      class="artist-modal-card"
    >
      <n-form :model="editArtistForm" layout="vertical">
        <n-form-item label="🎙️ 歌手艺名 (用于词曲作者、表演者栏)">
          <n-input v-model:value="editArtistForm.stage_name" placeholder="例如：月栖洲" />
        </n-form-item>
        <n-form-item label="👤 真实姓名 (版权实名，用于结算收益)">
          <n-input v-model:value="editArtistForm.real_name" placeholder="请输入身份证姓名" />
        </n-form-item>
        
        <div class="modal-section-title">🔗 平台歌手主页链接 (保存后自动解析歌手 ID)</div>
        
        <n-form-item label="网易云音乐人主页 Link">
          <n-input v-model:value="neteaseUrl" placeholder="https://music.163.com/#/artist?id=..." />
        </n-form-item>

        <n-form-item label="QQ音乐人主页 Link">
          <n-input v-model:value="qqUrl" placeholder="https://y.qq.com/n/ryqq_v2/singer/..." />
        </n-form-item>
      </n-form>

      <template #action>
        <n-space justify="end">
          <n-button secondary @click="showEditArtist = false">取消</n-button>
          <n-button type="primary" :loading="savingArtist" @click="saveArtistProfile">保存更改</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import PipelineBoard from '../components/PipelineBoard.vue';
import { usePipelineStore } from '../stores/pipeline';

const pipelineStore = usePipelineStore();
const { publishAccounts, backupTracks, artist, error } = storeToRefs(pipelineStore);
const loading = ref(false);

// 歌手编辑相关
const showEditArtist = ref(false);
const savingArtist = ref(false);
const editArtistForm = ref({ stage_name: '', real_name: '' });
const neteaseUrl = ref('');
const qqUrl = ref('');

const loginTagType = (status) => ({
  connected: 'success', expired: 'error', unconfigured: 'warning', unknown: 'default',
}[status] || 'default');

const backupTagType = (status) => ({
  backed_up: 'success', syncing: 'info', failed: 'error', unrecorded: 'warning',
}[status] || 'default');

const publishTagType = (status) => ({
  published: 'success', publishing: 'info', rejected: 'error', pending: 'warning',
}[status] || 'default');

// 从主页 URL 中提取歌手 ID
const parseArtistId = (url) => {
  if (!url) return '未登记';
  try {
    const u = new URL(url);
    if (url.includes('y.qq.com')) {
      const match = u.pathname.match(/\/singer\/([A-Za-z0-9]+)/);
      return match ? match[1] : '未知';
    }
    if (url.includes('music.163.com')) {
      const id = u.searchParams.get('id') || u.hash.split('id=')[1];
      return id || '未知';
    }
  } catch (e) {
    // 可能是老旧的普通文本
  }
  const matches = url.match(/id=(\d+)/) || url.match(/\/singer\/([A-Za-z0-9]+)/);
  return matches ? matches[1] : '已登记';
};

// 解析歌曲的平台 ID
const getSongId = (release) => {
  if (!release) return '';
  if (release.song_id) return release.song_id;
  if (release.url) {
    try {
      const u = new URL(release.url);
      if (release.url.includes('song')) {
        const id = u.searchParams.get('id') || u.pathname.match(/\/song\/([0-9]+)/)?.[1];
        if (id) return id;
      }
    } catch(e) {}
  }
  return release.note || '';
};

// 解析歌曲链接
const getSongUrl = (release) => {
  return release?.url || '';
};

const loadBoard = async () => {
  loading.value = true;
  try {
    await pipelineStore.loadPublishBoard();
  } finally {
    loading.value = false;
  }
};

const openEditArtistModal = () => {
  const currentArtist = artist.value || {};
  editArtistForm.value = {
    stage_name: currentArtist.stage_name || '',
    real_name: currentArtist.real_name || ''
  };
  
  // 回填平台链接
  const profiles = currentArtist.platform_profiles || [];
  const netease = profiles.find(p => p.platform === '网易云音乐');
  const qq = profiles.find(p => p.platform === 'QQ音乐');
  neteaseUrl.value = netease ? netease.url : '';
  qqUrl.value = qq ? qq.url : '';
  
  showEditArtist.value = true;
};

const saveArtistProfile = async () => {
  savingArtist.value = true;
  try {
    const updatedProfiles = [];
    if (neteaseUrl.value.trim()) {
      updatedProfiles.push({
        platform: '网易云音乐',
        url: neteaseUrl.value.trim(),
        has_page: true,
        type: 'Artist Profile'
      });
    }
    if (qqUrl.value.trim()) {
      updatedProfiles.push({
        platform: 'QQ音乐',
        url: qqUrl.value.trim(),
        has_page: true,
        type: 'Official Artist'
      });
    }
    
    await pipelineStore.saveArtist({
      stage_name: editArtistForm.value.stage_name.trim(),
      real_name: editArtistForm.value.real_name.trim(),
      platform_profiles: updatedProfiles
    });
    showEditArtist.value = false;
  } catch (e) {
    console.error(e);
  } finally {
    savingArtist.value = false;
  }
};

onMounted(() => { void loadBoard(); });
</script>

<style scoped>
.tab-content-container { display: flex; flex-direction: column; gap: var(--vf-space-4); }
.publish-header { display: flex; align-items: center; justify-content: space-between; gap: var(--vf-space-3); }
.tab-title { margin: 0; color: var(--vf-text-1); font-size: 15px; font-weight: 600; }
.tab-subtitle, .account-detail { margin: var(--vf-space-1) 0 0; color: var(--vf-text-3); font-size: 12px; }
.truth-alert { margin: 0; }

/* 🎙️ 歌手身份卡片毛玻璃样式 */
.artist-identity-card {
  background: rgba(22, 22, 26, 0.45) !important;
  backdrop-filter: blur(12px) !important;
  -webkit-backdrop-filter: blur(12px) !important;
  border: 1px solid rgba(255, 255, 255, 0.05) !important;
  border-radius: 14px !important;
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.25) !important;
}

.identity-header-title {
  display: flex;
  flex-direction: column;
}

.identity-header-sub {
  font-size: 11px;
  color: var(--vf-text-3);
  font-weight: normal;
  margin-top: 2px;
}

.identity-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
  padding: 8px 0;
}

@media (min-width: 768px) {
  .identity-layout {
    grid-template-columns: 1fr 1.3fr;
  }
}

.identity-info-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-right: none;
  padding-right: 0;
}

@media (min-width: 768px) {
  .identity-info-box {
    border-right: 1px solid rgba(255, 255, 255, 0.06);
    padding-right: 24px;
  }
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.info-label {
  color: var(--vf-text-2);
}

.info-value-highlight {
  color: var(--vf-primary);
  font-weight: 600;
  font-size: 15px;
  text-shadow: 0 0 10px rgba(129, 140, 248, 0.25);
}

.info-value {
  color: var(--vf-text-1);
  font-weight: 500;
}

.info-value-auth {
  color: var(--vf-ok);
  font-weight: 500;
}

.platform-profiles-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.profile-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--vf-text-2);
  margin-bottom: 4px;
}

.profile-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.profile-item {
  display: flex;
  align-items: center;
  font-size: 13px;
  background: rgba(255, 255, 255, 0.02);
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.platform-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--vf-primary);
  margin-right: 8px;
  box-shadow: 0 0 6px var(--vf-primary);
}

.platform-name {
  color: var(--vf-text-1);
  font-weight: 500;
  margin-right: 6px;
}

.profile-id-badge {
  font-size: 11px;
  color: var(--vf-text-2);
  background: rgba(129, 140, 248, 0.12);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}

.profile-link-btn {
  margin-left: auto;
  font-size: 11px;
  color: var(--vf-primary);
  text-decoration: none;
  transition: opacity 0.2s;
}

.profile-link-btn:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.no-profiles-tip {
  font-size: 12px;
  color: var(--vf-warn);
  padding: 10px;
}

/* 账号卡片毛玻璃样式 */
.account-card {
  background: rgba(22, 22, 26, 0.45) !important;
  backdrop-filter: blur(12px) !important;
  -webkit-backdrop-filter: blur(12px) !important;
  border: 1px solid rgba(255, 255, 255, 0.04) !important;
  border-radius: 12px !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2) !important;
  transition: border-color 0.3s;
}

.account-card:hover {
  border-color: rgba(129, 140, 248, 0.2) !important;
}

.account-heading, .release-row { 
  display: flex; 
  align-items: center; 
  justify-content: space-between; 
  gap: var(--vf-space-2); 
}

.account-label-text {
  font-weight: 600;
  color: var(--vf-text-1);
  font-size: 14px;
}

.release-heading { 
  margin: var(--vf-space-4) 0 var(--vf-space-2); 
  color: var(--vf-text-2); 
  font-size: 12px; 
  font-weight: 600;
}

.releases-list {
  max-height: 250px;
  overflow-y: auto;
  padding-right: 4px;
}

.release-row {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
  padding: 6px 10px;
  border-radius: 8px;
}

.release-left-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
  margin-right: 8px;
}

.release-title { 
  overflow: hidden; 
  color: var(--vf-text-1); 
  font-size: 13px; 
  text-overflow: ellipsis; 
  white-space: nowrap; 
}

.song-id-tag {
  font-size: 10px;
  color: var(--vf-text-3);
  font-family: monospace;
}

.song-link-icon {
  text-decoration: none;
  font-size: 12px;
  transition: transform 0.2s;
}
.song-link-icon:hover {
  transform: scale(1.2);
}

.empty-releases {
  padding: 24px 0 !important;
}

.backup-card {
  background: rgba(22, 22, 26, 0.42) !important;
  backdrop-filter: blur(12px) !important;
  -webkit-backdrop-filter: blur(12px) !important;
  border: 1px solid rgba(255, 255, 255, 0.04) !important;
  border-radius: 12px !important;
}

.publish-error { margin: 0; color: var(--vf-err); font-size: 12px; }

/* 弹窗细节 */
.modal-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--vf-text-2);
  margin: 16px 0 8px;
}
</style>
