(function () {
  const MaxParentSdk = {
    postMessage: function (event, payload) {
      const message = {
        type: event,
        payload: payload || {},
        source: 'max-parent-sdk',
      };

      if (window.parent && window.parent !== window) {
        window.parent.postMessage(message, '*');
        return message;
      }

      return message;
    },

    openMiniApp: function (url, payload) {
      const target = payload && payload.url ? payload.url : url;
      if (window.parent && window.parent !== window) {
        this.postMessage('open-mini-app', { url: target, payload: payload || {} });
      }

      if (target) {
        window.location.href = target;
      }
      return target;
    },

    closeMiniApp: function () {
      if (window.parent && window.parent !== window) {
        this.postMessage('close-mini-app', {});
      }

      if (window.history && window.history.length > 1) {
        window.history.back();
      }
    },
  };

  window.MaxParentSdk = MaxParentSdk;
})();
