    (function () {
      var el = document.getElementById("netState");
      function update() {
        el.innerHTML = navigator.onLine
          ? '<span class="online">Back online. Retry is ready.</span>'
          : "Still offline. Your queued work remains local.";
      }
      window.addEventListener("online", update);
      window.addEventListener("offline", update);
      update();
    })();
  
