/**
 * 音频库与全局播放器状态。
 * API：GET /api/audio-list、DELETE /api/audio/{filename}
 */
import { reactive, ref } from 'vue';
import { defineStore } from 'pinia';
import { api, toMessage } from '../api';

export const useLibraryStore = defineStore('library', () => {
  const audioFiles = ref([]);
  const player = reactive({ url: '', filename: '', visible: false });
  const error = ref('');

  const loadAudioList = async () => {
    error.value = '';
    try {
      const data = await api.audioList();
      audioFiles.value = data.files || [];
      return audioFiles.value;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  const playAudio = (url, filename) => {
    Object.assign(player, { url, filename, visible: true });
  };

  const closePlayer = () => {
    Object.assign(player, { url: '', filename: '', visible: false });
  };

  const deleteAudio = async (filename) => {
    error.value = '';
    try {
      const data = await api.deleteAudio(filename);
      await loadAudioList();
      return data;
    } catch (cause) {
      error.value = cause.message;
      throw cause;
    }
  };

  return { audioFiles, player, error, loadAudioList, playAudio, closePlayer, deleteAudio };
});
