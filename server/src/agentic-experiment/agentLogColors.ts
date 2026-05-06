const RESET = "\x1b[0m";
const DIM = "\x1b[2m";
const BOLD = "\x1b[1m";

export type AgentLogStyle =
  | "init"
  | "initDetail"
  | "status"
  | "prose"
  | "toolStart"
  | "toolDone"
  | "toolProgress"
  | "toolFinished"
  | "toolError"
  | "toolXtra"
  | "toolPuppeteer"
  | "toolGeneric"
  | "heartbeat"
  | "warn"
  | "error"
  | "notify"
  | "task"
  | "crawlHeader"
  | "crawlLabel"
  | "crawlValue"
  | "limitation"
  | "terminalHeader"
  | "terminalResult"
  | "success"
  | "meta"
  | "finalSummary";

const STYLES: Record<AgentLogStyle, string> = {
  init: `${BOLD}\x1b[36m`,
  initDetail: `${DIM}\x1b[36m`,
  status: "\x1b[34m",
  prose: "",
  toolStart: "\x1b[33m",
  toolDone: "\x1b[32m",
  toolProgress: "\x1b[36m",
  toolFinished: "\x1b[32m",
  toolError: "\x1b[31m",
  toolXtra: "\x1b[35m",
  toolPuppeteer: "\x1b[34m",
  toolGeneric: "\x1b[33m",
  heartbeat: `${DIM}\x1b[90m`,
  warn: "\x1b[33m",
  error: "\x1b[31m",
  notify: "\x1b[34m",
  task: `${DIM}\x1b[34m`,
  crawlHeader: `${BOLD}\x1b[36m`,
  crawlLabel: `${DIM}\x1b[37m`,
  crawlValue: "\x1b[37m",
  limitation: "\x1b[33m",
  terminalHeader: `${BOLD}\x1b[35m`,
  terminalResult: "\x1b[37m",
  success: "\x1b[32m",
  meta: `${DIM}\x1b[90m`,
  finalSummary: "\x1b[37m",
};

function isColorEnabled() {
  if (process.env.NO_COLOR !== undefined) {
    return false;
  }

  if (process.env.FORCE_COLOR !== undefined) {
    return true;
  }

  return Boolean(process.stdout.isTTY);
}

export function colorize(style: AgentLogStyle, text: string) {
  if (!isColorEnabled()) {
    return text;
  }

  const open = STYLES[style];
  if (!open) {
    return text;
  }

  return `${open}${text}${RESET}`;
}

export function writeStyled(
  style: AgentLogStyle,
  text: string,
  stream: NodeJS.WriteStream = process.stdout
) {
  stream.write(colorize(style, text));
}

export function logStyled(style: AgentLogStyle, text: string) {
  console.log(colorize(style, text));
}

export function warnStyled(style: AgentLogStyle, text: string) {
  console.warn(colorize(style, text));
}

export function errorStyled(style: AgentLogStyle, text: string) {
  console.error(colorize(style, text));
}
