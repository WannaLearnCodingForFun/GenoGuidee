/* Swallow Chrome-extension inject noise so Next.js does not treat it as an app crash. */
(function () {
  if (typeof window === "undefined" || window.__GG_EXT_ERR_FILTER__) return;
  window.__GG_EXT_ERR_FILTER__ = true;

  function noisy(value) {
    if (value == null) return false;
    var text = "";
    if (typeof value === "string") text = value;
    else if (typeof value === "object") {
      text = String(value.message || value);
      if (value.stack) text += "\n" + value.stack;
    } else {
      text = String(value);
    }
    return (
      /WELLDONE Wallet/i.test(text) ||
      /chrome-extension:\/\//i.test(text) ||
      /moz-extension:\/\//i.test(text) ||
      /safari-web-extension:\/\//i.test(text)
    );
  }

  function noisyArgs(args) {
    for (var i = 0; i < args.length; i++) {
      if (noisy(args[i])) return true;
    }
    return false;
  }

  function wrap(method) {
    var current = console[method].bind(console);
    function filtered() {
      if (noisyArgs(arguments)) return;
      return current.apply(console, arguments);
    }
    try {
      Object.defineProperty(console, method, {
        configurable: true,
        get: function () {
          return filtered;
        },
        set: function (fn) {
          if (typeof fn === "function") current = fn.bind(console);
        },
      });
    } catch (_) {
      console[method] = filtered;
    }
  }

  wrap("error");
  wrap("warn");

  window.addEventListener(
    "error",
    function (event) {
      if (
        (event.filename && /^(chrome|moz|safari-web)-extension:\/\//i.test(event.filename)) ||
        noisy(event.message) ||
        noisy(event.error)
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true,
  );

  window.addEventListener(
    "unhandledrejection",
    function (event) {
      if (noisy(event.reason)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true,
  );
})();
