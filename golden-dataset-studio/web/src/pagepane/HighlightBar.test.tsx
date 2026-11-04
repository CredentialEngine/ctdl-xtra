import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import { HighlightBar, type BarAction } from "./HighlightBar";
import { barAt } from "./PagePane";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const sel = { text: "LIMITATION", css_path: "html > p", char_start: 0, char_end: 10, prefix: "", suffix: "" };

describe("HighlightBar (sme-fixes §1)", () => {
  it("shows the actions it is given, with their tooltips; a click runs one on the selection and closes the bar", async () => {
    const run = vi.fn();
    const done = vi.fn();
    const actions: BarAction[] = [
      { id: "comment", label: "💬", tone: "note", title: "Comment on this text", run },
      { id: "ceterms:description", label: "description", title: "Label it as the description", run },
    ];
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(<HighlightBar at={{ sel, x: 40, y: 12 }} actions={actions} onDone={done} />));
    const btns = [...box.querySelectorAll<HTMLButtonElement>(".gpp-hb")];
    expect(btns.map((b) => [b.textContent, b.title])).toEqual([["💬", "Comment on this text"], ["description", "Label it as the description"]]);
    expect(btns[0].getAttribute("aria-label")).toBe("Comment on this text");  // an icon: named by its tooltip
    expect(box.querySelector<HTMLElement>(".gpp-hbar")!.style.left).toBe("40px");
    await act(async () => btns[1].click());
    expect(run).toHaveBeenCalledWith(sel);
    expect(done).toHaveBeenCalled();
    act(() => root.unmount());
    box.remove();
  });

  it("sits just above the selection, scaled to the pane, or below it when there's no room above", () => {
    expect(barAt(sel, { left: 100, top: 200, bottom: 220 }, 0.5)).toEqual({ sel, x: 50, y: 64 });
    expect(barAt(sel, { left: 10, top: 20, bottom: 40 }, 1)).toEqual({ sel, x: 10, y: 46 });
  });
});
