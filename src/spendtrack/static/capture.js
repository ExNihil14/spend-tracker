(function () {
  var form = document.getElementById("capture-form");
  var date = document.getElementById("capture-date");
  var clientId = document.getElementById("capture-client-id");
  var token = document.getElementById("capture-token");
  var CLIENT_KEY = "spendtrack-capture-client-id";
  var TOKEN_KEY = "spendtrack-capture-token";

  function newId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "cap-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  if (date && !date.value) {
    var now = new Date();
    var month = String(now.getMonth() + 1).padStart(2, "0");
    var day = String(now.getDate()).padStart(2, "0");
    date.value = now.getFullYear() + "-" + month + "-" + day;
  }

  if (clientId) {
    var savedId = window.localStorage.getItem(CLIENT_KEY);
    clientId.value = savedId || newId();
    window.localStorage.setItem(CLIENT_KEY, clientId.value);
  }

  if (token) {
    var savedToken = window.localStorage.getItem(TOKEN_KEY);
    if (savedToken) token.value = savedToken;
    token.addEventListener("input", function () {
      window.localStorage.setItem(TOKEN_KEY, token.value.trim());
    });
  }

  document.body.addEventListener("htmx:configRequest", function (event) {
    if (!token || event.detail.path !== "/api/transactions") return;
    var value = token.value.trim();
    if (value) event.detail.headers["X-Spendtrack-Token"] = value;
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    if (!form || event.detail.elt !== form || !clientId) return;
    var xhr = event.detail.xhr;
    if (event.detail.successful && xhr && xhr.status === 200) {
      clientId.value = newId();
      window.localStorage.setItem(CLIENT_KEY, clientId.value);
    }
  });
})();
