// The page pane (spec §7.2, §7.7, §9): the whole saved page in a browser-like frame, with highlights,
// highlight-to-annotate, "pick a block", and the HTML view. Embedded by the Rules and Records tabs.
export { PagePane, prefetchPages, renderUrl, LAYOUT_WIDTH } from "./PagePane";
export type { PageTab, PagePaneProps } from "./PagePane";
export type { Highlight, HighlightKind } from "./paint";
export type { CapturedSelection } from "./dom";
export { cssPathOf, findText, resolveOffsets, captureRange } from "./dom";
