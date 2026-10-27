// Word diff for the Evals rows: golden value → xtra's value. Longest common subsequence over words (and the spaces
// between them); a value is at most a few hundred words, so the table stays small.
export interface Part { op: "same" | "del" | "ins"; text: string }

const MAX_TOKENS = 1500;

export function wordDiff(a: string, b: string): Part[] {
  const x = a.split(/(\s+)/).filter(Boolean), y = b.split(/(\s+)/).filter(Boolean);
  if (x.length > MAX_TOKENS || y.length > MAX_TOKENS) return [{ op: "del", text: a }, { op: "ins", text: b }];
  const n = x.length, m = y.length;
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out: Part[] = [];
  const push = (op: Part["op"], text: string) => {
    const last = out[out.length - 1];
    if (last && last.op === op) last.text += text; else out.push({ op, text });
  };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { push("same", x[i]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) push("del", x[i++]);
    else push("ins", y[j++]);
  }
  while (i < n) push("del", x[i++]);
  while (j < m) push("ins", y[j++]);
  return out;
}
