(() => {
  const config = window.DEBATE_ARGUMENT_STATUS || {
    statuses: {},
    actions: {},
    showGlossJa: false,
  };

  window.debateArgumentLabel = function debateArgumentLabel(status) {
    const meta = (config.statuses || {})[status];
    if (!meta) return String(status || "");
    if (config.showGlossJa && meta.gloss_ja) return `${meta.label_en}（${meta.gloss_ja}）`;
    return meta.label_en;
  };

  window.debateActionLabel = function debateActionLabel(action) {
    const meta = (config.actions || {})[action];
    return meta ? meta.label_en : String(action || "");
  };
})();
