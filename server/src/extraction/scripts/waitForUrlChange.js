// @ts-ignore
window.__xtra__waitForUrlChangeScript = ({ oldUrl, timeout, pollInterval }) => {
  return new Promise(resolve => {
    const start = Date.now();

    function checkUrl() {
      // @ts-ignore
      if (window.location.href !== oldUrl) {
        // @ts-ignore
        resolve(window.location.href);
      } else if (Date.now() - start > timeout) {
        // @ts-ignore
        reject(new Error('Timeout waiting for URL change')); // timed out, return current URL
      } else {
        setTimeout(checkUrl, pollInterval);
      }
    }

    checkUrl();
  });
};