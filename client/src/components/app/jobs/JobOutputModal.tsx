import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AGENTIC_RECIPE_CONFIG_JOB_RETENTION_HOURS } from "@common/recipe";
import { useEffect, useRef, type ReactNode } from "react";

interface JobOutputModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  logs: string[];
  isRunning: boolean;
  renderLine?: (line: string) => ReactNode;
}

export default function JobOutputModal({
  open,
  onOpenChange,
  logs,
  isRunning,
  renderLine,
}: JobOutputModalProps) {
  const outputRef = useRef<HTMLDivElement>(null);
  const logText = logs.join("\n");

  useEffect(() => {
    if (!open || !isRunning || !outputRef.current) {
      return;
    }
    outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [open, isRunning, logText]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[66vw] w-11/12 max-h-[70vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Job output</DialogTitle>
          <DialogDescription>
            After the job finishes, output
            remains available for {AGENTIC_RECIPE_CONFIG_JOB_RETENTION_HOURS}{" "}
            hours.
          </DialogDescription>
        </DialogHeader>
        <div
          ref={outputRef}
          className="mt-4 flex-1 min-h-[240px] max-h-[50vh] overflow-y-auto rounded-md border bg-muted/40 p-4"
        >
          {logs.length === 0 ? (
            <p className="font-serif text-sm text-muted-foreground">
              Waiting for output…
            </p>
          ) : (
            <div className="font-serif text-sm space-y-1">
              {logs.map((line, index) => (
                <p key={index} className="whitespace-pre-wrap">
                  {renderLine ? renderLine(line) : line}
                </p>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
