/**
 * 音频库与全局播放器状态。
 * API：GET /api/audio-list、DELETE /api/audio/{filename}
 */
import { reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';

/** 音频库单条记录（LibraryTab 消费的形状）。 */
interface AudioFile {
  filename: string;
  url: string;
  created?: string;
  size?: number;
}

/** 全局播放器可见状态（GlobalPlayer 消费）。 */
interface PlayerState {
  url: string;
  filename: string;
  visible: boolean;
}

export const useLibraryStore = defineStore('library', () => {
  const audioFiles = ref<AudioFile[]>([]);
  const player = reactive<PlayerState>({ url: '', filename: '', visible: false });
  const error = ref('');

  const loadAudioList = async (): Promise<AudioFile[]> => {
    error.value = '';
    try {
      const data = await api.audioList();
      // api 层把 audio-list 的 files 标成 unknown[]，这里按实际消费形状窄化。
      audioFiles.value = (data.files || []) as AudioFile[];
      return audioFiles.value;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  const playAudio = (url: string, filename?: string) => {
    Object.assign(player, { url, filename, visible: true });
  };

  const closePlayer = () => {
    Object.assign(player, { url: '', filename: '', visible: false });
  };

  const deleteAudio = async (filename: string): Promise<{ ok: boolean }> => {
    error.value = '';
    try {
      const data = await api.deleteAudio(filename);
      await loadAudioList();
      return data;
    } catch (cause) {
      error.value = await toMessage(cause);
      throw cause;
    }
  };

  return { audioFiles, player, error, loadAudioList, playAudio, closePlayer, deleteAudio };
});
