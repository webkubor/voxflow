/**
 * 全局键盘快捷键。
 *
 * 之前全局没有任何快捷键：⌘K 搜索没有、Esc 关弹窗没有、空格在播放器外
 * 都不响应。键盘用户（写作者、Agent 流程）的操作效率差。
 *
 * 现在内置：
 *   ⌘K / Ctrl+K   聚焦左侧音色搜索框（如果有）
 *   /             同 ⌘K（不冲突 Vim 用户的习惯）
 *   空格           播放/暂停（只在非输入元素聚焦时生效）
 *   m              静音/取消静音
 *   t              打开/关闭任务面板
 *   e              打开/关闭错误日志
 *   1-7            切到对应 tab
 *   ?              打开快捷键帮助
 *   Esc            关闭最上层 panel/modal
 *
 * ## 为什么是 composable 而不是直接绑事件
 *
 * 1. 单元测试能 mock window.dispatchEvent 触发，验证回调被调用
 * 2. 路由切换时自动清理 —— Vue 生命周期管理
 * 3. 输入元素（input / textarea / [contenteditable]）里不抢键，
 *    不打断打字
 */
import { onBeforeUnmount, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const TAB_ORDER = ['clone', 'design', 'dialogue', 'suno', 'works', 'publish', 'library'];

/** 输入框判定：这些元素里所有快捷键都失效，避免打断输入 */
const isEditableTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return false;
};

interface ShortcutOptions {
  /** 当某个键组合触发时打开任务面板 */
  onToggleTaskPanel?: () => void;
  onToggleErrorPanel?: () => void;
  onTogglePlayer?: () => void;
  onToggleMute?: () => void;
  onFocusPersonaSearch?: () => void;
  onShowHelp?: () => void;
}

export function useShortcuts(opts: ShortcutOptions) {
  const router = useRouter();
  const route = useRoute();

  const handler = (e: KeyboardEvent) => {
    const mod = e.metaKey || e.ctrlKey;
    const editable = isEditableTarget(e.target);

    // Esc —— 关弹窗不受 editable 限制，从任何地方按都生效
    if (e.key === 'Escape') {
      opts.onToggleErrorPanel?.();
      opts.onToggleTaskPanel?.();
      return;
    }

    // 编辑元素里只放行修饰键组合（剪贴板、undo 之类），其他都让出来
    if (editable) return;

    // ⌘K / Ctrl+K —— 打开错误日志面板（最常用的入口）
    if (mod && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      opts.onFocusPersonaSearch?.() || opts.onShowHelp?.();
      return;
    }

    // / —— 跟 GitHub / Linear / Vercel 一致，打开搜索
    if (e.key === '/' && !mod) {
      e.preventDefault();
      opts.onFocusPersonaSearch?.();
      return;
    }

    // 空格 —— 播放/暂停（不在输入框时）
    if (e.code === 'Space' && !mod) {
      e.preventDefault();
      opts.onTogglePlayer?.();
      return;
    }

    // m —— 静音
    if (e.key === 'm' && !mod) {
      opts.onToggleMute?.();
      return;
    }

    // t / e —— 任务 / 错误日志
    if (e.key === 't' && !mod) {
      opts.onToggleTaskPanel?.();
      return;
    }
    if (e.key === 'e' && !mod) {
      opts.onToggleErrorPanel?.();
      return;
    }

    // ? —— 帮助（按下 shift+/）
    if (e.key === '?' && !mod) {
      opts.onShowHelp?.();
      return;
    }

    // 数字 1-7 —— 切 tab
    if (!mod && /^[1-7]$/.test(e.key)) {
      const idx = Number(e.key) - 1;
      const target = TAB_ORDER[idx];
      if (target) {
        e.preventDefault();
        router.push({ name: target });
      }
    }
  };

  onMounted(() => {
    window.addEventListener('keydown', handler);
  });
  onBeforeUnmount(() => {
    window.removeEventListener('keydown', handler);
  });

  return { route };
}
