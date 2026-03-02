import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { trpc } from "@/utils";
import { Trash2 } from "lucide-react";
import { useState, useCallback } from "react";

export function ProxySettingsForm() {
  const proxyPreviewsQuery = trpc.settings.proxyPreviews.useQuery(undefined, {
    refetchOnWindowFocus: false,
  });
  const proxyEnabledQuery = trpc.settings.detail.useQuery({
    key: "PROXY_ENABLED",
  });
  const proxyEnabledMutation = trpc.settings.setProxyEnabled.useMutation();
  const addProxyUrlMutation = trpc.settings.addProxyUrl.useMutation();
  const removeProxyUrlMutation = trpc.settings.removeProxyUrl.useMutation();
  const [newProxyUrl, setNewProxyUrl] = useState("");
  const [confirmProxyToggle, setConfirmProxyToggle] = useState(false);
  const [proxyConfirmOpen, setProxyConfirmOpen] = useState(false);
  const [deleteConfirmIndex, setDeleteConfirmIndex] = useState<number | null>(
    null
  );
  const { toast } = useToast();

  const redactedList = proxyPreviewsQuery.data ?? [];

  const handleAdd = useCallback(async () => {
    const url = newProxyUrl.trim();
    if (!url) {
      toast({
        title: "Validation Error",
        description: "Enter a proxy URL to add.",
        variant: "destructive",
      });
      return;
    }
    try {
      await addProxyUrlMutation.mutateAsync(url);
      setNewProxyUrl("");
      toast({ title: "Added", description: "Proxy URL added successfully." });
      proxyPreviewsQuery.refetch();
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to add proxy URL. Check the URL format.",
        variant: "destructive",
      });
    }
  }, [newProxyUrl, addProxyUrlMutation, toast, proxyPreviewsQuery]);

  const handleRemoveClick = useCallback((index: number) => {
    setDeleteConfirmIndex(index);
  }, []);

  const handleRemoveConfirm = useCallback(async () => {
    if (deleteConfirmIndex === null) return;
    const index = deleteConfirmIndex;
    setDeleteConfirmIndex(null);
    try {
      await removeProxyUrlMutation.mutateAsync(index);
      toast({ title: "Removed", description: "Proxy URL removed." });
      proxyPreviewsQuery.refetch();
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to remove proxy URL.",
        variant: "destructive",
      });
    }
  }, [
    deleteConfirmIndex,
    removeProxyUrlMutation,
    toast,
    proxyPreviewsQuery,
  ]);

  const onProxyToggle = async () => {
    try {
      await proxyEnabledMutation.mutateAsync(!proxyEnabledQuery.data?.value);
      await proxyEnabledQuery.refetch();
    } finally {
      setProxyConfirmOpen(false);
    }
  };

  const proxiesLoaded =
    proxyPreviewsQuery.isFetched && !proxyPreviewsQuery.isLoading;

  const isLoading =
    addProxyUrlMutation.isLoading ||
    removeProxyUrlMutation.isLoading ||
    proxyPreviewsQuery.isLoading ||
    proxyEnabledMutation.isLoading ||
    proxyEnabledQuery.isLoading;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        handleAdd();
      }}
    >
      <Card className="flex-1 w-[440px]">
        <CardHeader>
          <CardTitle>Proxy Settings</CardTitle>
          <CardDescription>
            Activating a proxy is helpful in overcoming rate limits or <br />
            blocking by anti-scraping measures. <br />
            The proxy is currently{" "}
            <strong>
              {proxyEnabledQuery.data?.value ? "enabled" : "disabled"}
            </strong>
            .
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <Dialog
            open={
              proxyEnabledQuery.isFetched &&
              proxiesLoaded &&
              proxyConfirmOpen
            }
            onOpenChange={setProxyConfirmOpen}
          >
            <DialogTrigger asChild>
              <Button variant="destructive">
                {proxyEnabledQuery.data?.value
                  ? "Disable Proxy"
                  : "Enable Proxy"}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Are you absolutely sure?</DialogTitle>
                <DialogDescription className="pt-2">
                  This will{" "}
                  {proxyEnabledQuery.data?.value ? "DISABLE" : "ENABLE"} the
                  proxy for all requests.
                </DialogDescription>
              </DialogHeader>
              <div className="items-top flex space-x-2">
                <Checkbox
                  id="terms1"
                  onCheckedChange={(e) => setConfirmProxyToggle(!!!e)}
                />
                <div className="grid gap-1.5 leading-none">
                  <label
                    htmlFor="terms1"
                    className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                  >
                    I understand the consequences
                  </label>
                  <p className="text-sm text-muted-foreground">
                    {proxyEnabledQuery.data?.value
                      ? "DISABLE the proxy for all requests."
                      : "ENABLE the proxy for all requests."}
                  </p>
                  <Button
                    variant="destructive"
                    disabled={confirmProxyToggle}
                    onClick={onProxyToggle}
                    className="mt-4"
                  >
                    {proxyEnabledQuery.data?.value
                      ? "Disable Proxy"
                      : "Enable Proxy"}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
          <Dialog
            open={deleteConfirmIndex !== null}
            onOpenChange={(open) => !open && setDeleteConfirmIndex(null)}
          >
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Remove proxy?</DialogTitle>
                <DialogDescription>
                  This will remove the proxy URL from your configuration. You
                  can add it back later if needed.
                </DialogDescription>
              </DialogHeader>
              <div className="flex justify-end gap-2 pt-4">
                <Button
                  variant="outline"
                  onClick={() => setDeleteConfirmIndex(null)}
                >
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  onClick={handleRemoveConfirm}
                  disabled={removeProxyUrlMutation.isLoading}
                >
                  Remove
                </Button>
              </div>
            </DialogContent>
          </Dialog>
          <div className="grid gap-2">
            <Label>Proxy URLs</Label>
            <p className="text-sm text-muted-foreground">
              Add new proxy URLs or remove existing ones. Credentials are stored
              encrypted and never exposed to the UI.
            </p>
            {redactedList.length > 0 && (
              <div className="space-y-2">
                <span className="text-sm font-medium">Configured proxies:</span>
                <ul className="space-y-2">
                  {redactedList.map((preview, index) => (
                    <li
                      key={index}
                      className="flex items-center gap-2 rounded-md border px-3 py-2"
                    >
                      <code className="flex-1 min-w-0 break-all font-mono text-sm">
                        {preview}
                      </code>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={() => handleRemoveClick(index)}
                        disabled={isLoading}
                        aria-label={`Remove proxy ${index + 1}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex gap-2">
              <Input
                placeholder="https://username:password@proxy.com:port"
                disabled={isLoading}
                value={newProxyUrl}
                onChange={(e) => setNewProxyUrl(e.target.value)}
                className="flex-1"
              />
              <Button
                type="submit"
                variant="secondary"
                disabled={isLoading}
              >
                Add proxy URL
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </form>
  );
}
