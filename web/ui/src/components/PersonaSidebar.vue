<template>
  <transition name="sider-slide">
    <aside v-if="!collapsed" class="voice-sider">
      <div class="sider-header">
        <div class="sider-title-row">
          <Icon name="voice" size="sm" />
          <h3>音色库</h3>
          <span class="count">{{ personas.length }}</span>
        </div>
        <button class="add-btn" @click="$emit('addPersona')" title="注册新音色">
          <Icon name="plus" size="sm" />
        </button>
      </div>

      <div v-if="personas.length > 5" class="sider-search">
        <Icon name="search" size="sm" class="search-icon" />
        <input
          ref="searchInput"
          v-model="keyword"
          type="text"
          placeholder="搜索音色…（按 / 聚焦）"
          class="search-input"
        />
        <button v-if="keyword" class="search-clear" @click="keyword = ''" title="清除">
          <Icon name="close" size="sm" />
        </button>
      </div>

      <div class="sider-list">
        <div
          v-for="p in filteredPersonas"
          :key="p.key"
          class="voice-item"
          :class="{ 'is-selected': selectedPersona === p.key }"
          tabindex="0"
          role="button"
          :aria-pressed="selectedPersona === p.key"
          @click="select(p.key)"
          @keydown.enter.prevent="select(p.key)"
          @keydown.space.prevent="select(p.key)"
        >
          <!-- 试听进度铺底 -->
          <div v-if="previewKey === p.key" class="voice-progress" :style="{ width: previewProgress + '%' }"></div>

          <div class="voice-row">
            <n-avatar round :size="32" :style="{ background: 'var(--vf-bg-4)', color: 'var(--vf-primary)', flex: 'none' }">
              {{ (p.name || p.key).charAt(0).toUpperCase() }}
            </n-avatar>
            <div class="voice-main">
              <div class="voice-head">
                <span class="voice-name" :title="p.name || p.key">{{ p.name || p.key }}</span>
                <span class="voice-status" :class="p.has_audio ? 'ok' : 'none'">
                  {{ p.has_audio ? '✓' : '○' }}
                </span>
              </div>
              <p class="voice-desc" :title="p.desc || p.instruction">
                {{ p.desc || p.instruction || '已装载声音特征' }}
              </p>
            </div>
          </div>

          <div class="voice-actions" @click.stop>
            <button
              v-if="p.has_audio"
              class="icon-btn"
              :title="previewKey === p.key ? '暂停试听' : '试听'"
              @click="togglePreview(p.key)"
            >
              <Icon :name="previewKey === p.key ? 'pause' : 'play'" size="sm" />
            </button>
            <button class="icon-btn" title="编辑" @click="$emit('editPersona', p.key)">
              <Icon name="edit" size="sm" />
            </button>
            <button class="icon-btn danger" title="删除" @click="$emit('deletePersona', p.key)">
              <Icon name="trash" size="sm" />
            </button>
          </div>
        </div>

        <div v-if="filteredPersonas.length === 0" class="empty">
          <p v-if="keyword">没有匹配「{{ keyword }}」的音色</p>
          <p v-else>暂无音色资产</p>
          <span v-if="!keyword">点击右上角 ✚ 注册新音色</span>
        </div>
      </div>
    </aside>
  </transition>

  <!-- 折叠态：只露手柄 -->
  <button
    v-if="collapsed"
    class="sider-rail"
    title="展开音色库"
    @click="$emit('toggleCollapse')"
  >
    <Icon name="chevron-right" size="sm" />
    <span class="rail-label">音色</span>
    <span class="rail-count">{{ personas.length }}</span>
  </button>
</template>

<script setup>
/**
 * 音色库侧栏 —— 独立成组件，让 MainLayout 不再关心 persona 的渲染细节。
 *
 * ## 折叠
 *
 * 默认展开；当主区空间紧张（用户主动折叠）时缩成右侧 64px 宽的窄条。
 * 不用侧边抽屉 —— 抽屉藏起来会让 persona 被遗忘，常驻窄条至少能提醒
 * 「这里还有东西」。
 *
 * ## 试听进度
 *
 * 进度条用 absolute 铺底，不占布局空间 —— 卡片高度不跳动。
 */
import { computed, nextTick, ref } from 'vue';
import { useVoicesStore } from '../stores/voices';
import { storeToRefs } from 'pinia';
import Icon from './Icon.vue';

defineProps({
  collapsed: { type: Boolean, default: false },
});
defineEmits(['toggleCollapse', 'addPersona', 'editPersona', 'deletePersona']);

const voicesStore = useVoicesStore();
const { personas, selectedPersona, previewKey, previewProgress } = storeToRefs(voicesStore);
const { selectPersona, togglePreview } = voicesStore;

const keyword = ref('');
const searchInput = ref(null);
const personasArr = computed(() =>
  Object.entries(personas.value).map(([key, p]) => ({ key, ...p })),
);
const filteredPersonas = computed(() => {
  const k = keyword.value.trim().toLowerCase();
  if (!k) return personasArr.value;
  return personasArr.value.filter(
    (p) => (p.name || '').toLowerCase().includes(k) || p.key.toLowerCase().includes(k),
  );
});

const select = (key) => voicesStore.selectPersona(key);

/** 暴露给父组件触发：被父级的全局快捷键调用 */
const focusSearch = () => {
  nextTick(() => searchInput.value?.focus());
};
defineExpose({ focusSearch });
</script>

<style scoped>
.voice-sider {
  display: flex;
  flex-direction: column;
  width: var(--vf-sider-w);
  background: var(--vf-bg-1);
  border-right: 1px solid var(--vf-border);
  user-select: none;
  overflow: hidden;
}

/* 折叠态窄条 */
.sider-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: var(--vf-sider-w-collapsed);
  background: var(--vf-bg-1);
  border: none;
  border-right: 1px solid var(--vf-border);
  border-radius: 0;
  padding: var(--vf-space-4) 0;
  color: var(--vf-text-2);
  cursor: pointer;
  font-size: 11px;
  transition: color 0.15s, background 0.15s;
}
.sider-rail:hover {
  color: var(--vf-primary);
  background: var(--vf-bg-hover);
}
.rail-label {
  writing-mode: vertical-rl;
  letter-spacing: 0.1em;
}
.rail-count {
  background: var(--vf-primary-soft);
  color: var(--vf-primary);
  border-radius: var(--vf-radius-full);
  padding: 1px 6px;
  font-weight: 600;
}

/* header */
.sider-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--vf-space-4);
  border-bottom: 1px solid var(--vf-border);
}
.sider-title-row {
  display: flex;
  align-items: center;
  gap: var(--vf-space-2);
  color: var(--vf-text-2);
}
.sider-title-row h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
}
.count {
  font-size: 11px;
  background: var(--vf-bg-3);
  color: var(--vf-text-2);
  padding: 1px 7px;
  border-radius: var(--vf-radius-full);
  font-weight: 600;
}
.add-btn {
  background: var(--vf-primary-soft);
  color: var(--vf-primary);
  border: 1px solid transparent;
  border-radius: var(--vf-radius-sm);
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s var(--vf-ease);
}
.add-btn:hover {
  background: var(--vf-primary);
  color: white;
  transform: translateY(-1px);
}

/* 搜索 */
.sider-search {
  position: relative;
  padding: var(--vf-space-3) var(--vf-space-4);
  border-bottom: 1px solid var(--vf-border);
}
.search-icon {
  position: absolute;
  left: calc(var(--vf-space-4) + 6px);
  top: 50%;
  transform: translateY(-50%);
  color: var(--vf-text-3);
}
.search-input {
  width: 100%;
  background: var(--vf-bg-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-sm);
  color: var(--vf-text-1);
  font-size: 12px;
  padding: 6px 28px 6px 28px;
  outline: none;
  transition: border-color 0.15s;
}
.search-input:focus {
  border-color: var(--vf-border-focus);
}
.search-clear {
  position: absolute;
  right: calc(var(--vf-space-4) + 6px);
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--vf-text-3);
  cursor: pointer;
  padding: 2px;
}
.search-clear:hover { color: var(--vf-text-1); }

/* 卡片列表 */
.sider-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--vf-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--vf-space-2);
}

.voice-item {
  position: relative;
  padding: var(--vf-space-2) var(--vf-space-3);
  border: 1px solid var(--vf-border);
  border-radius: var(--vf-radius-md);
  background: var(--vf-bg-2);
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.15s, background 0.15s, transform 0.15s var(--vf-ease);
}
.voice-item:hover {
  background: var(--vf-bg-3);
  border-color: var(--vf-border-strong);
}
.voice-item.is-selected {
  border-color: var(--vf-primary);
  background: var(--vf-primary-soft);
}
.voice-item:focus-visible {
  outline: 2px solid var(--vf-primary);
  outline-offset: 2px;
}

.voice-progress {
  position: absolute;
  left: 0; bottom: 0;
  height: 2px;
  background: var(--vf-primary);
  transition: width 0.1s linear;
}

.voice-row {
  display: flex;
  align-items: flex-start;
  gap: var(--vf-space-2);
  margin-bottom: var(--vf-space-2);
}
.voice-main {
  flex: 1;
  min-width: 0;
}
.voice-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vf-space-2);
  margin-bottom: 2px;
}
.voice-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--vf-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.voice-status {
  font-size: 10px;
  flex: none;
  padding: 1px 5px;
  border-radius: var(--vf-radius-full);
}
.voice-status.ok {
  background: var(--vf-ok-soft);
  color: var(--vf-ok);
}
.voice-status.none {
  background: var(--vf-bg-3);
  color: var(--vf-text-3);
}
.voice-desc {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--vf-text-3);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.voice-actions {
  display: flex;
  align-items: center;
  gap: var(--vf-space-1);
  justify-content: flex-end;
  border-top: 1px dashed var(--vf-border);
  padding-top: var(--vf-space-2);
}
.icon-btn {
  background: transparent;
  border: none;
  border-radius: var(--vf-radius-xs);
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--vf-text-3);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.icon-btn:hover {
  background: var(--vf-bg-hover);
  color: var(--vf-text-1);
}
.icon-btn.danger:hover { color: var(--vf-err); }

.empty {
  text-align: center;
  padding: var(--vf-space-8) var(--vf-space-3);
  color: var(--vf-text-3);
}
.empty p { margin: 0 0 var(--vf-space-1); font-size: 13px; color: var(--vf-text-2); }
.empty span { font-size: 11px; }

/* 折叠 transition */
.sider-slide-enter-active,
.sider-slide-leave-active {
  transition: width 0.2s var(--vf-ease), opacity 0.2s;
}
.sider-slide-enter-from,
.sider-slide-leave-to {
  width: 0;
  opacity: 0;
}
</style>
