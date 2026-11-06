// Native forms carry a server-rendered hidden token; JavaScript writes use the same token.
(() => {
  const token = () => document.querySelector('meta[name="csrf-token"]')?.content;
  document.addEventListener("htmx:configRequest", (event) => {
    event.detail.headers["X-CSRF-Token"] = token();
    event.detail.headers["X-CSP-Nonce"] = document.querySelector('meta[name="csp-nonce"]')?.content;
  });
  const originalFetch = window.fetch;
  window.fetch = (input, options = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    const method = (options.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
    if (url.origin === location.origin && !["GET", "HEAD", "OPTIONS"].includes(method)) {
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      headers.set("X-CSRF-Token", token());
      options = { ...options, headers };
    }
    return originalFetch.call(window, input, options);
  };
})();
