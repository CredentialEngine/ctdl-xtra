import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { prettyPrintDate, trpc } from "@/utils";

interface AuditLogModalProps {
  extractionId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function AuditLogModal({
  extractionId,
  open,
  onOpenChange,
}: AuditLogModalProps) {
  const { data: auditLogs, isLoading } = trpc.extractions.auditLogs.useQuery(
    { extractionId },
    { enabled: open }
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[66vw] w-11/12 max-h-[70vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Extraction Audit Log</DialogTitle>
          <DialogDescription>
            Complete history of actions performed on this extraction.
          </DialogDescription>
        </DialogHeader>
        <div className="mt-4">
          {isLoading ? (
            <div className="text-sm text-muted-foreground">Loading...</div>
          ) : !auditLogs || auditLogs.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No audit log entries found.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {auditLogs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="text-xs">
                      {prettyPrintDate(log.createdAt)}
                    </TableCell>
                    <TableCell className="text-xs">
                      {log.user?.name || log.user?.email || "Unknown User"}
                    </TableCell>
                    <TableCell className="text-xs font-medium">
                      {log.action}
                    </TableCell>
                    <TableCell className="text-xs">
                      {log.reason || "-"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
