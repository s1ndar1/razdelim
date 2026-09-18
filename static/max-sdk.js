(function () {
  const MaxSdk = {
    getInitData: function () {
      if (window.WebApp && window.WebApp.initData) {
        return window.WebApp.initData;
      }
      return '';
    },

    getUser: function () {
      const initData = this.getInitData();
      if (!initData) {
        return null;
      }

      const params = new URLSearchParams(initData);
      const rawUser = params.get('user');
      if (!rawUser) {
        return null;
      }

      try {
        return JSON.parse(rawUser);
      } catch (error) {
        return null;
      }
    },

    showAlert: function (message) {
      if (window.WebApp && typeof window.WebApp.showAlert === 'function') {
        window.WebApp.showAlert(message);
        return;
      }

      window.alert(message);
    },

    close: function () {
      if (window.WebApp && typeof window.WebApp.close === 'function') {
        window.WebApp.close();
        return;
      }

      if (window.history && window.history.length > 1) {
        window.history.back();
      }
    },
  };

  window.MaxSdk = MaxSdk;
})();
