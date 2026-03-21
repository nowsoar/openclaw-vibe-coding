const Storage = (() => {
  const KEYS = {
    HIGH_SCORE: 'tetris_high_score',
    TOTAL_TIME: 'tetris_total_time',
    PROGRESS:   'tetris_progress',
  };

  return {
    getHighScore() {
      return parseInt(localStorage.getItem(KEYS.HIGH_SCORE) || '0');
    },

    setHighScore(score) {
      if (score > this.getHighScore()) {
        localStorage.setItem(KEYS.HIGH_SCORE, score);
        return true;
      }
      return false;
    },

    getTotalTime() {
      return parseInt(localStorage.getItem(KEYS.TOTAL_TIME) || '0');
    },

    addTotalTime(ms) {
      const total = this.getTotalTime() + Math.max(0, ms);
      localStorage.setItem(KEYS.TOTAL_TIME, total);
      return total;
    },

    saveProgress(state) {
      try {
        localStorage.setItem(KEYS.PROGRESS, JSON.stringify(state));
      } catch (e) {}
    },

    loadProgress() {
      try {
        const data = localStorage.getItem(KEYS.PROGRESS);
        return data ? JSON.parse(data) : null;
      } catch (e) {
        return null;
      }
    },

    clearProgress() {
      localStorage.removeItem(KEYS.PROGRESS);
    },
  };
})();
