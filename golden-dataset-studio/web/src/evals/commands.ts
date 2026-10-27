// "Run it yourself": shell commands with one option per line, continued with backslashes. Commands stored on one line
// (by runs made before the Studio wrote them this way) get the same shape.
export function multiline(cmd: string): string {
  if (cmd.includes("\\\n")) return cmd;
  const lines: string[][] = [];
  for (const t of cmd.match(/'[^']*'|"[^"]*"|\S+/g) ?? []) {
    if (!lines.length || t.startsWith("--")) lines.push([t]);
    else lines[lines.length - 1].push(t);
  }
  return lines.map((l) => l.join(" ")).join(" \\\n  ");
}
