import type { CatalogList, CatalogSummary } from "../types";

interface Props {
  list: CatalogList | null;
  error: string | null;
  onOpen: (cid: string) => void;
}

const when = (runId: string) => runId.replace("T", " ").replace(/Z$/, "").replace(/-(\d\d)-(\d\d)$/, ":$1:$2");

function Progress({ card }: { card: CatalogSummary }) {
  const review = card.review;
  if (!review) return <p className="muted">No review started yet.</p>;
  const { accepted, rejected, total, flagged_pages: fp, flagged_items: fi } = review.counts;
  const pct = total ? Math.round((accepted / total) * 100) : 0;
  return (
    <div className="progress-block">
      <div className="progress" role="img" aria-label={`${pct}% accepted`}>
        <span style={{ width: `${pct}%` }} />
      </div>
      <p>
        <strong>{accepted}</strong> of {total} accepted
        {rejected > 0 && <span className="bad"> · {rejected} rejected</span>}
        {(fp > 0 || fi > 0) && (
          <span className="flag-mark">
            {" "}
            · ⚑ {fp} page{fp === 1 ? "" : "s"}, {fi} item{fi === 1 ? "" : "s"} flagged
          </span>
        )}
      </p>
    </div>
  );
}

function Card({ card, onOpen }: { card: CatalogSummary; onOpen: (cid: string) => void }) {
  return (
    <li className={`catalog-card ${card.ready ? "" : "not-ready"}`}>
      <div className="catalog-head">
        <h2>{card.catalog_folder}</h2>
        {card.ready ? (
          card.extraction?.stale ? (
            <span className="chip derived">rules changed since extract</span>
          ) : (
            <span className="chip status accepted">ready</span>
          )
        ) : (
          <span className="chip none">not ready</span>
        )}
      </div>
      <p className="muted small">
        {card.seed_url} · crawled {when(card.run_id)} · {card.pages} pages
      </p>
      <dl>
        <dt>Ruleset</dt>
        <dd>
          {card.ruleset ? (
            <>
              {card.ruleset.id} <span className="chip">v{card.ruleset.version}</span> · {card.ruleset.rules} rules
            </>
          ) : (
            <span className="bad">{card.ruleset_error ?? "none"}</span>
          )}
        </dd>
        <dt>Extraction</dt>
        <dd>
          {card.extraction ? (
            <>
              {card.extraction.id} · {card.extraction.records} records
              {card.extraction.stale && (
                <span className="flag-mark"> (made with ruleset v{card.extraction.ruleset_version})</span>
              )}
            </>
          ) : (
            "none yet"
          )}
        </dd>
      </dl>
      <Progress card={card} />
      {card.hint && <p className="hint-box">{card.hint}</p>}
      <button className="primary" disabled={!card.ready} onClick={() => onOpen(card.cid)}>
        {card.review ? "Continue review" : "Start review"}
      </button>
    </li>
  );
}

export default function Landing({ list, error, onOpen }: Props) {
  return (
    <div className="landing">
      <header>
        <h1>xTRA Review</h1>
        <p className="muted">Choose a ruleset to review.</p>
      </header>
      {error && <div className="banner error" role="alert">{error}</div>}
      {!list && !error && <div className="loading">Loading…</div>}
      {list && list.catalogs.length === 0 && (
        <div className="card empty-card">
          No crawl run has a ruleset yet. Add <code>rulesets/&lt;catalog&gt;/rules.json</code> for a crawled
          catalog and reload this page.
        </div>
      )}
      {list && (
        <ul className="catalog-list">
          {list.catalogs.map((card) => (
            <Card key={card.cid} card={card} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </div>
  );
}
