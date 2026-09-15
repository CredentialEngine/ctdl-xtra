import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { AGENTIC_RECIPE_CONFIG_JOB_RETENTION_HOURS } from "@common/recipe";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

interface JobOutputModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  logs: string[];
  isRunning: boolean;
  renderLine?: (line: string) => ReactNode;
  isStageOrStatusLine?: (line: string) => boolean;
}

export default function JobOutputModal({
  open,
  onOpenChange,
  logs,
  isRunning,
  renderLine,
  isStageOrStatusLine,
}: JobOutputModalProps) {
  const outputRef = useRef<HTMLDivElement>(null);
  const [showAll, setShowAll] = useState(false);
  const displayedLogs = useMemo(() => {
    if (showAll || !isStageOrStatusLine) {
      return logs;
    }
    return logs.filter(isStageOrStatusLine);
  }, [isStageOrStatusLine, logs, showAll]);
  const displayedLogText = displayedLogs.join("\n");

  useEffect(() => {
    if (!open || !isRunning || !outputRef.current) {
      return;
    }
    outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [open, isRunning, displayedLogText]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[66vw] w-11/12 max-h-[70vh] min-w-0 overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Job output</DialogTitle>
          <DialogDescription>
            Public output from the running job. After the job finishes, output
            remains available for {AGENTIC_RECIPE_CONFIG_JOB_RETENTION_HOURS}{" "}
            hours.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center space-x-2">
          <Checkbox
            id="show-all-output"
            checked={showAll}
            onCheckedChange={(checked) => setShowAll(checked === true)}
          />
          <Label htmlFor="show-all-output" className="font-normal">
            Show all
          </Label>
        </div>
        <div
          ref={outputRef}
          className="mt-4 flex-1 min-h-[240px] min-w-0 max-h-[50vh] overflow-y-auto rounded-md border bg-muted/40 p-4"
        >
          {logs.length === 0 ? (
            <p className="font-serif text-sm text-muted-foreground">
              Waiting for output…
            </p>
          ) : (
            <div className="font-serif text-sm space-y-1 min-w-0 w-full">
              {displayedLogs.map((line, index) => (
                <div
                  key={index}
                  className="min-w-0 w-full max-w-full overflow-x-hidden whitespace-pre-wrap"
                >
                  {renderLine ? renderLine(line) : line}
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
