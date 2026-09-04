import { parseXtraToolResult } from "./agenticRecipeEvents";
import type { AgentEvent } from "./types";

export class AgenticRecipeRunTracker {
  giveUpMessage: string | null = null;

  handleEvent(event: AgentEvent): void {
    if (event.type !== "tool" || event.isError) {
      return;
    }
    const parsed = parseXtraToolResult(event.message);
    if (parsed?.kind === "give_up" && parsed.message) {
      this.giveUpMessage = parsed.message;
    }
  }
}
