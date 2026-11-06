import { useEffect, useRef, useState } from "react";
import { contentUrl, getSource } from "../api";

interface Props {
  stem: string;
  url: string;
  highlight: string[];
}

export default function PagePane({ stem, url, highlight }: Props) {
  const [tab, setTab] = useState<"page" | "html">("page");
  const [source, setSource] = useState<string | null>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const latest = useRef(highlight);
  latest.current = highlight;

  const send = () =>
    frame.current?.contentWindow?.postMessage({ type: "highlight", paths: latest.current }, "*");

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.source === frame.current?.contentWindow && e.data?.type === "ready") send();
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    send();
  }, [highlight]);

  useEffect(() => {
    setSource(null);
    if (tab === "html") getSource(stem).then(setSource).catch((e) => setSource(String(e)));
  }, [tab, stem]);

  return (
    <section className="pane page-pane">
      <div className="pane-tabs">
        <button className={tab === "page" ? "on" : ""} onClick={() => setTab("page")}>Page</button>
        <button className={tab === "html" ? "on" : ""} onClick={() => setTab("html")}>HTML</button>
        <a href={url} target="_blank" rel="noreferrer" className="live-link" title={url}>
          open live page ↗
        </a>
      </div>
      <div className="notice">
        Showing only the page's own content (the site menu is left out), with the page's own
        styles. The highlighted element is where the rule read the value.
      </div>
      {tab === "page" ? (
        <iframe
          key={stem}
          ref={frame}
          title="Saved page"
          src={contentUrl(stem)}
          sandbox="allow-scripts"
        />
      ) : (
        <pre className="source">{source ?? "Loading…"}</pre>
      )}
    </section>
  );
}
