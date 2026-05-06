import type { SDKMessage } from "@anthropic-ai/claude-agent-sdk";
import { colorize, writeStyled } from "./agentLogColors";
import { shortToolName } from "./agentToolLog";
import type { ToolCallTracker } from "./agentToolResultLog";

export class AgentStreamPrinter {
  private inTool = false;
  private pendingLineBreak = false;

  handleStreamEvent(
    message: Extract<SDKMessage, { type: "stream_event" }>,
    tracker: ToolCallTracker
  ) {
    const event = message.event;

    if (event.type === "content_block_start") {
      if (event.content_block.type === "tool_use") {
        tracker.remember(
          event.content_block.id,
          event.content_block.name
        );
        if (this.pendingLineBreak) {
          process.stdout.write("\n");
          this.pendingLineBreak = false;
        }

        writeStyled(
          "toolStart",
          `[Using ${shortToolName(event.content_block.name)}...]`
        );
        this.inTool = true;
      }
      return;
    }

    if (event.type === "content_block_delta") {
      if (event.delta.type === "text_delta" && !this.inTool) {
        process.stdout.write(colorize("prose", event.delta.text));
        this.pendingLineBreak = true;
      }
      return;
    }

    if (event.type === "content_block_stop" && this.inTool) {
      writeStyled("toolDone", " done\n");
      this.inTool = false;
      this.pendingLineBreak = false;
    }
  }

  finishTurn() {
    if (this.pendingLineBreak) {
      process.stdout.write("\n");
      this.pendingLineBreak = false;
    }
  }
}
