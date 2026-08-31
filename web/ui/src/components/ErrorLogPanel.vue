<template>
  <transition name="error-panel">
    <aside v-if="open" class="error-panel" role="complementary" aria-label="错误日志">
      <header class="ep-head">
        <div class="ep-head-left">
          <Icon name="warning" size="sm" />
          <span>错误日志</span>
          <span class="ep-count">{{ errorLogStore.unreadCount }}</span>
        </div>
        <div class="ep-head-right">
          <button class="head-btn" title="全部清空" :disabled="!records.length" @click="confirmClear">
            <Icon name="trash" size="sm" />
          </button>
          <button class="head-btn" title="关闭" @click="$emit('close')">
            <Icon name="close" size="sm" />
          </button>
        </div>
      </header>

      <div class="ep-body scroll-y">
        <div v-if="!records.length" class="ep-empty">
          <Icon name="check" size="md" />
          <span>一切正常，没有错误记录</span>
        </div>

        <article
          v-for="r in records"
          :key="r.id"
          class="ep-record"
          :class="`severity-${r.severity}`"
        >
          <header class="ep-record-head">
            <span class="ep-tag" :class="`tag-${r.severity}`">{{ severityLabel(r.severity) }}</span>
            <span v-if="r.method && r.url" class="ep-method">{{ r.method }} {{ shortUrl(r.url) }}</span>
            <span v-else-if="r.context?.action" class="ep-method">{{ r.context.action }}</span>
            <span class="ep-time">{{ formatTime(r.timestamp) }}</span>
            <span v-if="r.count > 1" class="ep-count-badge">×{{ r.count }}</span>
          </header>

          <p class="ep-message">{{ r.message }}</p>

          <div v-if="r.status || r.requestId || r.context?.tags" class="ep-meta">
            <span v-if="r.status" class="meta-pill">HTTP {{ r.status }}</span>
            <span v-if="r.requestId" class="meta-pill mono">ID: {{ r.requestId }}</span>
            <span
              v-for="(v, k) in r.context?.tags"
              :key="String(k)"
              class="meta-pill"
            >
              {{ k }}={{ v }}
            </span>
          </div>

          <details class="ep-detail">
            <summary class="ep-detail-head">
              <Icon name="chevron-right" size="sm" />
              <span>完整堆栈</span>
            </summary>
            <pre class="ep-detail-pre">{{ r.detail }}</pre>
          </details>

          <footer class="ep-actions">
            <button class="action-btn" title="复制错误详情" @click="copyDetail(r)">
              <Icon :name="copiedId === r.id ? 'check' : 'layers'" size="sm" />
              <span>{{ copiedId === r.id ? '已复制' : '复制详情' }}</span>
            </button>
            <button class="action-btn" title="从日志移除" @click="errorLogStore.dismiss(r.id)">
              <Icon name="close" size="sm" />
              <span>移除</span>
            </button>
          </footer>
        </article>
      </div>
    </aside>
  </transition>
</template>

<script setup>
/**
 * 错误日志面板 —— 取代「3 秒 toast 一闪就没」的体验。
 *
 * 任何 caught 错误通过 tasksStore.reportError 进来，都能在面板里看到
 * 完整 HTTP 上下文 + 堆栈 + 「复制详情」一键贴到 issue。
 *
 * 同指纹错误 60 秒内重复 → 计数合并，不刷屏。
 */
import { computed, ref } from 'vue';
import copy from 'copy-to-clipboard';
import { useErrorLogStore } from '../stores/errorLog';
import Icon from './Icon.vue';

defineProps({ open: { type: Boolean, default: true } });
defineEmits(['close']);

const errorLogStore = useErrorLogStore();
const records = computed(() => errorLogStore.records);
const copiedId = ref('');

const SEVERITY_LABEL = { warning: '警告', error: '错误', fatal: '致命' };
const severityLabel = (s) => SEVERITY_LABEL[s] || s;

const formatTime = (ts) => {
  const d = new Date(ts);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
};

const shortUrl = (url) => {
  try {
    const u = new URL(url, window.location.origin);
    return u.pathname;
  } catch {
    return url;
  }
};

const copyDetail = (r) => {
  const ok = copy(r.detail);
  if (ok) {
    copiedId.value = r.id;
    setTimeout(() => { if (copiedId.value === r.id) copiedId.value = ''; }, 1500);
  }
};

const confirmClear = () => {
  if (confirm(`清空全部 ${records.value.length} 条错误记录？`)) {
    errorLogStore.clearAll();
  }
};
</script>

<style scoped>
.error-panel {
  position: fixed;
  top: calc(var(--vf-header-h) + var(--vf-space-3));
  right: var(--vf-space-3);
  width: 380px;
  max-height: calc(100vh - var(--vf-header-h) - var(--vf-player-h) - var(--vf-space-7));
  background: var(--vf-bg-1);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  box-shadow: var(--vf-shadow-elevated);
  z-index: 110;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.error-panel.severity-warning { border-left: 3px solid var(--vf-warn); }

.error-panel-enter-active,
.error-panel-leave-active {
  transition: transform 0.2s var(--vf-ease), opacity 0.2s;
}
.error-panel-enter-from,
.error-panel-leave-to {
  transform: translateX(20px);
  opacity: 0;
}

/* head */
.ep-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--vf-space-3) var(--vf-space-4);
  background: var(--vf-bg-2);
  border-bottom: 1px solid var(--vf-border);
}
.ep-head-left {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}
.ep-count {
  background: var(--vf-err-soft);
  color: var(--vf-err);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
  font-size: 10px;
  font-weight: 600;
}
.ep-head-right { display: flex; gap: var(--vf-space-1); }
.head-btn {
  background: transparent;
  border: none;
  color: var(--vf-text-3);
  width: 26px;
  height: 26px;
  border-radius: var(--vf-radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
}
.head-btn:hover:not(:disabled) {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
}
.head-btn:disabled { opacity: 0.3; cursor: not-allowed; }

/* body */
.ep-body {
  padding: var(--vf-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-2);
}

.ep-empty {
  text-align: center;
  padding: var(--vf-space-7) var(--vf-space-3);
  color: var(--vf-ok);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--vf-space-2);
  font-size: 12px;
}

/* record */
.ep-record {
  padding: var(--vf-space-3);
  background: var(--vf-bg-2);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  border-left: 3px solid var(--vf-text-3);
}
.ep-record.severity-warning { border-left-color: var(--vf-warn); }
.ep-record.severity-error { border-left-color: var(--vf-err); }
.ep-record.severity-fatal {
  border-left-color: var(--vf-err);
  background: linear-gradient(90deg, var(--vf-err-soft) 0%, var(--vf-bg-2) 50%);
}

.ep-record-head {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  margin-bottom: var(--vf-space-2);
  flex-wrap: wrap;
  font-size: 11px;
}
.ep-tag {
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
  font-weight: 600;
  font-size: 10px;
  flex: none;
}
.ep-tag.tag-warning { background: var(--vf-warn-soft); color: var(--vf-warn); }
.ep-tag.tag-error { background: var(--vf-err-soft); color: var(--vf-err); }
.ep-tag.tag-fatal { background: var(--vf-err); color: white; }

.ep-method {
  font-family: ui-monospace, monospace;
  color: var(--vf-text-2);
  font-size: 10px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ep-time {
  color: var(--vf-text-3);
  font-variant-numeric: tabular-nums;
  flex: none;
}
.ep-count-badge {
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
  padding: 1px 6px;
  border-radius: var(--vf-radius-full);
  font-size: 10px;
  font-weight: 600;
  flex: none;
}

.ep-message {
  margin: 0 0 var(--vf-space-2);
  font-size: 12px;
  line-height: 1.5;
  color: var(--vf-text-1);
  word-break: break-word;
}

.ep-meta {
  display: flex;
  gap: var(--vf-space-2);
  flex-wrap: wrap;
  margin-bottom: var(--vf-space-2);
}
.meta-pill {
  font-size: 10px;
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
}
.meta-pill.mono {
  font-family: ui-monospace, monospace;
  letter-spacing: 0.02em;
}

.ep-detail {
  border-top: 1px dashed var(--vf-border);
  padding-top: var(--vf-space-2);
}
.ep-detail-head {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--vf-text-3);
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.ep-detail-head::-webkit-details-marker { display: none; }
.ep-detail-head .vf-icon { transition: transform 0.15s var(--vf-ease); }
.ep-detail[open] .ep-detail-head .vf-icon { transform: rotate(90deg); }

.ep-detail-pre {
  margin: var(--vf-space-2) 0 0;
  padding: var(--vf-space-2);
  background: var(--vf-bg-0);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-xs);
  font-family: ui-monospace, monospace;
  font-size: 10px;
  line-height: 1.5;
  color: var(--vf-text-2);
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.ep-actions {
  display: flex;
  gap: var(--vf-space-2);
  margin-top: var(--vf-space-2);
}
.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  color: var(--vf-text-2);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}
.action-btn:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
  border-color: var(--vf-border-strong);
}
</style>
