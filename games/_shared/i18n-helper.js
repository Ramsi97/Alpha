// Usage per game:
//   const STRINGS = { en: { title: "2048" }, am: { title: "..." }, om: { title: "..." } };
//   const t = AlphaGoI18n(STRINGS, AlphaGo.lang);  // AlphaGo.lang set from the `start` message
//   t("title")
window.AlphaGoI18n = function (strings, lang) {
  const fallback = strings.en || {};
  const dict = strings[lang] || fallback;
  return function t(key) {
    return dict[key] !== undefined ? dict[key] : fallback[key] !== undefined ? fallback[key] : key;
  };
};
