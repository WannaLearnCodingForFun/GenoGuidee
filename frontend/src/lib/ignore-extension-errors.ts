declare global {
  interface Window {
    __GG_EXT_ERR_FILTER__?: boolean;
  }
}

function noisy(value: unknown): boolean {
  if (value == null) return false;
  let text = "";
  if (typeof value === "string") text = value;
  else if (typeof value === "object") {
    const err = value as { message?: string; stack?: string };
    text = String(err.message ?? value);
    if (err.stack) text += `\n${err.stack}`;
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

export function installExtensionErrorFilter(): void {
  if (typeof window === "undefined" || window.__GG_EXT_ERR_FILTER__) return;
  window.__GG_EXT_ERR_FILTER__ = true;

  const wrap = (method: "error" | "warn") => {
    let current = console[method].bind(console);
    const filtered = (...args: unknown[]) => {
      if (args.some((arg) => noisy(arg))) return;
      current(...args);
    };
    try {
      Object.defineProperty(console, method, {
        configurable: true,
        get: () => filtered,
        set: (fn: typeof console.error) => {
          if (typeof fn === "function") current = fn.bind(console);
        },
      });
    } catch {
      console[method] = filtered as typeof console.error;
    }
  };

  wrap("error");
  wrap("warn");

  window.addEventListener(
    "error",
    (event) => {
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
    (event) => {
      if (noisy(event.reason)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true,
  );
}

installExtensionErrorFilter();
