import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import { barLeft, HighlightBar, type BarAction } from "./HighlightBar";
import { barAt } from "./PagePane";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const sel = { text: "LIMITATION", css_path: "html > p", char_start: 0, char_end: 10, prefix: "", suffix: "" };

describe("HighlightBar (sme-fixes §1)", () => {
  it("shows the actions it is given, with their tooltips; a click runs one on the selection and closes the bar", async () => {
    const run = vi.fn();
    const done = vi.fn();
    const actions: BarAction[] = [
      { id: "comment", label: <span className="ico" />, tone: "note", title: "Comment on this text", run },
      { id: "ceterms:description", label: "description", title: "Label it as the description", run },
    ];
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(<HighlightBar at={{ sel, x: 40, y: 12 }} actions={actions} onDone={done} />));
    const btns = [...box.querySelectorAll<HTMLButtonElement>(".gpp-hb")];
    expect(btns.map((b) => [b.textContent, b.title])).toEqual([["", "Comment on this text"], ["description", "Label it as the description"]]);
    expect(btns[0].getAttribute("aria-label")).toBe("Comment on this text");  // an icon: named by its tooltip
    expect(box.querySelector<HTMLElement>(".gpp-hbar")!.style.left).toBe("40px");
    await act(async () => btns[1].click());
    expect(run).toHaveBeenCalledWith(sel);
    expect(done).toHaveBeenCalled();
    act(() => root.unmount());
    box.remove();
  });

  it("a keepOpen action (the comment bubble) leaves the bar up and shows pressed; the others close it", async () => {
    const run = vi.fn();
    const done = vi.fn();
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(<HighlightBar at={{ sel, x: 40, y: 12 }} onDone={done} actions={[
      { id: "comment", label: <span className="ico" />, tone: "note", title: "Comment on this text", keepOpen: true, run },
      { id: "in", label: "✓ In answer", tone: "in", title: "In the answer", run }]} />));
    const [c, i] = [...box.querySelectorAll<HTMLButtonElement>(".gpp-hb")];
    await act(async () => c.click());
    expect(done).not.toHaveBeenCalled();
    expect(c.getAttribute("aria-pressed")).toBe("true");
    await act(async () => i.click());
    expect(run).toHaveBeenCalledTimes(2);
    expect(done).toHaveBeenCalled();
    act(() => root.unmount());
    box.remove();
  });

  it("a hover bar: tells when the pointer comes onto it and leaves, and a keepOpen action pins it", async () => {
    const pointer = vi.fn();
    const pin = vi.fn();
    const box = document.createElement("div");
    document.body.appendChild(box);
    const root = createRoot(box);
    await act(async () => root.render(<HighlightBar at={{ sel, x: 40, y: 12, hover: "value" }} onDone={vi.fn()} onPointer={pointer} onPin={pin}
      actions={[{ id: "comment", label: <span className="ico" />, tone: "note", title: "Comment on this text", keepOpen: true, run: vi.fn() }]} />));
    const bar = box.querySelector<HTMLElement>(".gpp-hbar")!;
    await act(async () => { bar.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, relatedTarget: document.body })); });
    await act(async () => { bar.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body })); });
    expect(pointer.mock.calls).toEqual([[true], [false]]);
    await act(async () => box.querySelector<HTMLButtonElement>(".gpp-hb")!.click());
    expect(pin).toHaveBeenCalled();
    act(() => root.unmount());
    box.remove();
  });

  it("sits just above the selection, scaled to the pane, or below it when there's no room above", () => {
    expect(barAt(sel, { left: 100, right: 140, top: 200, bottom: 220 }, 0.5)).toEqual({ sel, x: 60, y: 64 });
    expect(barAt(sel, { left: 10, right: 30, top: 20, bottom: 40 }, 1)).toEqual({ sel, x: 20, y: 46 });
  });

  it("is centred over the selection and kept inside the pane: a selection at the right edge shifts it left", () => {
    expect(barLeft(300, 200, 600)).toBe(200);   // room on both sides: centred
    expect(barLeft(590, 200, 600)).toBe(396);   // near the right edge: its right side 4px inside the pane
    expect(barLeft(20, 200, 600)).toBe(4);      // near the left edge
    expect(barLeft(590, 200, 0)).toBe(490);     // pane not measured yet: centred
  });
});
