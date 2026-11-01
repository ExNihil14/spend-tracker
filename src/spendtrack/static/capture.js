(function () {
  var date = document.getElementById("capture-date");
  if (!date || date.value) return;
  var now = new Date();
  var month = String(now.getMonth() + 1).padStart(2, "0");
  var day = String(now.getDate()).padStart(2, "0");
  date.value = now.getFullYear() + "-" + month + "-" + day;
})();
