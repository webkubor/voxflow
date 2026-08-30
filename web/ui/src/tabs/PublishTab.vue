<template>
  <div class="tab-content-container">
    <div class="publish-header">
      <div>
        <h3 class="tab-title">音乐自动发布</h3>
        <p class="tab-subtitle">账号登录、平台曲目与云备份的同源状态</p>
      </div>
      <n-button secondary size="small" :loading="loading" @click="loadBoard">刷新状态</n-button>
    </div>

    <n-alert type="warning" :show-icon="false" class="truth-alert">
      未接入的平台登录检测或云备份不会被伪装成成功；请在台账记录实际状态后再以此页为准。
    </n-alert>

    <n-grid :cols="1" :m-cols="3" :x-gap="16" :y-gap="16" class="accounts-grid">
      <n-grid-item v-for="account in publishAccounts" :key="account.id">
        <n-card size="small" class="account-card">
          <template #header>
            <div class="account-heading">
              <span>{{ account.label }}</span>
              <n-tag size="small" :type="loginTagType(account.login.status)">
                登录：{{ account.login.label }}
              </n-tag>
            </div>
          </template>
          <p class="account-detail">{{ account.login.detail }}</p>
          <div class="release-heading">已记录曲目 · {{ account.releases.length }}</div>
          <n-space v-if="account.releases.length" vertical size="small">
            <div v-for="release in account.releases" :key="release.id" class="release-row">
              <span class="release-title">{{ release.title }}</span>
              <n-space size="small">
                <n-tag size="small" :type="publishTagType(release.status)">{{ release.status }}</n-tag>
                <n-tag size="small" :type="backupTagType(release.cloud_backup.status)">
                  {{ release.cloud_backup.label }}
                </n-tag>
              </n-space>
            </div>
          </n-space>
          <n-empty v-else size="small" description="暂无已记录发布曲目" />
        </n-card>
      </n-grid-item>
    </n-grid>

    <n-card size="small" class="backup-card" title="所有歌曲的云备份">
      <n-list v-if="tracks.length" bordered>
        <n-list-item v-for="track in tracks" :key="track.id">
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
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { usePipelineStore } from '../stores/pipeline';

const pipelineStore = usePipelineStore();
const { publishAccounts, tracks, error } = storeToRefs(pipelineStore);
const loading = ref(false);

const loginTagType = (status) => ({
  connected: 'success', expired: 'error', unconfigured: 'warning', unknown: 'default',
}[status] || 'default');

const backupTagType = (status) => ({
  backed_up: 'success', syncing: 'info', failed: 'error', unrecorded: 'warning',
}[status] || 'default');

const publishTagType = (status) => ({
  published: 'success', publishing: 'info', rejected: 'error', pending: 'warning',
}[status] || 'default');

const loadBoard = async () => {
  loading.value = true;
  try {
    await pipelineStore.loadPublishBoard();
  } finally {
    loading.value = false;
  }
};

onMounted(() => { void loadBoard(); });
</script>

<style scoped>
.tab-content-container { display: flex; flex-direction: column; gap: var(--vf-space-4); }
.publish-header { display: flex; align-items: center; justify-content: space-between; gap: var(--vf-space-3); }
.tab-title { margin: 0; color: var(--vf-text-1); font-size: 15px; }
.tab-subtitle, .account-detail { margin: var(--vf-space-1) 0 0; color: var(--vf-text-3); font-size: 12px; }
.truth-alert { margin: 0; }
.account-card, .backup-card { background: var(--vf-bg-1); border-color: var(--vf-bg-4); }
.account-heading, .release-row { display: flex; align-items: center; justify-content: space-between; gap: var(--vf-space-2); }
.release-heading { margin: var(--vf-space-4) 0 var(--vf-space-2); color: var(--vf-text-2); font-size: 12px; }
.release-title { overflow: hidden; color: var(--vf-text-1); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.publish-error { margin: 0; color: var(--vf-err); font-size: 12px; }
</style>
