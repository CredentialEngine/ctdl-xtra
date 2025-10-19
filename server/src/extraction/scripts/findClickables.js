window.__xtra__findClickablesScript = (element) => {
  console.log("findClickablesScript", element);
  debugger;
  // @ts-ignore
  function isClickable(el) {
    // Has inline onclick or role of button/link
    if (
      el.onclick ||
      el.getAttribute("role") === "button" ||
      el.tagName === "BUTTON" ||
      el.tagName === "A"
    ) {
      return true;
    }

    // Check CSS pointer-events and cursor
    // @ts-ignore
    const style = window.getComputedStyle(el);
    const hasPointerEvents = style.pointerEvents !== "none";
    const looksClickable = style.cursor === "pointer";

    return hasPointerEvents && looksClickable;
  }

  // @ts-ignore
  const descendants = element.querySelectorAll("*");

  for (const el of descendants) {
    if (isClickable(el)) {
      el.setAttribute("data-xtra-clickable", "true");
      el.setAttribute("data-xtra-clickable-id", getCssSelector(el));
    }
  }

  // @ts-ignore
  function getCssSelector(el) {
    // @ts-ignore
    if (!(el instanceof Element)) return null;

    // If the element has an ID, that is always the best selector
    if (el.id) {
      // @ts-ignore
      return `#${CSS.escape(el.id)}`;
    }

    const parts = [];

    // @ts-ignore
    while (el && el.nodeType === Node.ELEMENT_NODE) {
      let part = el.tagName.toLowerCase();

      // Include classes if present
      if (el.classList.length > 0) {
        const classes = [...el.classList]
          // @ts-ignore
          .map((c) => `.${CSS.escape(c)}`)
          .join("");
        part += classes;
      }

      // Include data attributes if present
      for (const attr of el.attributes) {
        if (attr.name.startsWith("data-")) {
          // @ts-ignore
          part += `[${attr.name}="${CSS.escape(attr.value)}"]`;
        }
      }

      // Check if this selector uniquely identifies the element
      // @ts-ignore
      if (document.querySelectorAll(part).length === 1) {
        parts.unshift(part);
        break; // we’re done — unique!
      }

      // Otherwise, fallback to nth-child
      const parent = el.parentNode;
      if (!parent) break;

      const siblings = [...parent.children];
      const index = siblings.indexOf(el) + 1;
      part += `:nth-child(${index})`;

      parts.unshift(part);
      el = parent;
    }

    return parts.join(" > ");
  }
};
