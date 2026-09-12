/**
 * AudioBus —— 全局音频播放协调器
 *
 * ## 为什么需要
 *
 * 之前 GlobalPlayer（底部播放器）和 PersonaSidebar（音色试听）各自有独立
 * 的 `<audio>` 元素，互不感知 —— 同时点两个会两首一起播，声音叠加。
 *
 * AudioBus 强制「同一时间只有一个音频源在播」：
 *   - GlobalPlayer 播一首 → 自动暂停 PersonaSidebar 的试听
 *   - PersonaSidebar 试听一个音色 → 自动暂停底部播放器
 *
 * ## 用法
 *
 * ```ts
 * const audio = ref<HTMLAudioElement | null>(null)
 *
 * onMounted(() => {
 *   if (audio.value) {
 *     audioBus.register('global-player', audio.value, {
 *       onPlay: () => { isPlaying.value = true },
 *       onPause: () => { isPlaying.value = false },
 *     })
 *   }
 * })
 *
 * onBeforeUnmount(() => {
 *   audioBus.unregister('global-player')
 * })
 * ```
 *
 * ## 频道 ID 约定
 *
 *   - `global-player`：底部播放器
 *   - `persona-preview`：音色试听
 *
 * 加新源加新 ID 就行。
 */

import { ref } from 'vue';

interface ChannelOpts {
  onPlay?: () => void;
  onPause?: () => void;
}

interface Channel {
  el: HTMLAudioElement;
  onPlay: () => void;
  onPause: () => void;
}

const activeChannelId = ref<string | null>(null);
const channels = new Map<string, Channel>();
const cleanups = new Map<string, () => void>();

/** 暂停除指定 ID 之外的所有音频源（el.pause() 会触发它们的 pause 事件） */
function pauseOthers(exceptId: string) {
  for (const [id, ch] of channels) {
    if (id !== exceptId && !ch.el.paused) ch.el.pause();
  }
}

export const audioBus = {
  /** 当前正在播放的频道 ID（响应式，可直接 watch / computed） */
  activeChannelId,

  /** 注册一个音频源。重复注册同 ID 会先注销旧的。 */
  register(id: string, el: HTMLAudioElement, opts: ChannelOpts = {}) {
    if (channels.has(id)) this.unregister(id);

    const onPlay = () => {
      pauseOthers(id);
      activeChannelId.value = id;
      opts.onPlay?.();
    };
    const onPause = () => {
      if (activeChannelId.value === id) activeChannelId.value = null;
      opts.onPause?.();
    };

    el.addEventListener('play', onPlay);
    el.addEventListener('pause', onPause);
    channels.set(id, { el, onPlay, onPause });
    cleanups.set(id, () => {
      el.removeEventListener('play', onPlay);
      el.removeEventListener('pause', onPause);
    });
  },

  /** 注销。组件卸载时调用，会顺手暂停该频道的音频。 */
  unregister(id: string) {
    cleanups.get(id)?.();
    cleanups.delete(id);
    const ch = channels.get(id);
    if (ch && !ch.el.paused) ch.el.pause();
    channels.delete(id);
    if (activeChannelId.value === id) activeChannelId.value = null;
  },

  /** 当前是不是这个 ID 在播 */
  isActive(id: string): boolean {
    return activeChannelId.value === id;
  },

  /** 强制停掉所有音频（场景切换时用） */
  stopAll() {
    for (const [, ch] of channels) {
      if (!ch.el.paused) ch.el.pause();
    }
    activeChannelId.value = null;
  },
};