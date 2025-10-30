import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
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
import { useState } from "react";

export function ProxySettingsForm() {
  const proxyUrlQuery = trpc.settings.detail.useQuery({
    key: "PROXY",
  });
  const proxyEnabledQuery = trpc.settings.detail.useQuery({
    key: "PROXY_ENABLED",
  });
  const proxyEnabledMutation = trpc.settings.setProxyEnabled.useMutation();
  const proxyUrlMutation = trpc.settings.setProxyUrl.useMutation();
  const [proxyUrl, setProxyUrl] = useState("");
  const [confirmProxyToggle, setConfirmProxyToggle] = useState(false);
  const [proxyConfirmOpen, setProxyConfirmOpen] = useState(false);
  const { toast } = useToast();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      await proxyUrlMutation.mutateAsync(proxyUrl);
      setProxyUrl("");
      toast({
        title: "Settings Updated",
        description: "The setting has been updated successfully.",
      });
      proxyUrlQuery.refetch();
      proxyEnabledQuery.refetch();
    } catch (error) {
      toast({
        title: "Error",
        description: "There was an error updating the setting.",
        variant: "destructive",
      });
    }
  };

  const onProxyToggle = async () => {
    try {
      await proxyEnabledMutation.mutateAsync(!proxyEnabledQuery.data?.value);
      await proxyEnabledQuery.refetch();
    } finally {
      setProxyConfirmOpen(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
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
              proxyUrlQuery.isFetched &&
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
          <div className="grid gap-2">
            <Label htmlFor="proxy_url">New proxy URL</Label>
            <div className="text-sm text-muted-foreground">
              {proxyUrlQuery.data?.encryptedPreview && (
                <>
                  The URL is currently set to{" "}
                  <code className="font-bold mb-2">
                    {proxyUrlQuery.data.encryptedPreview}
                  </code>
                  .
                </>
              )}
            </div>
            <Input
              id="proxy_url"
              placeholder="https://username:password@proxy.com:port"
              disabled={proxyUrlQuery?.isLoading}
              value={proxyUrl}
              onChange={(e) => setProxyUrl(e.target.value)}
              type="password"
            />
          </div>
        </CardContent>
        <CardFooter>
          <Button
            variant="outline"
            disabled={
              proxyUrlMutation?.isLoading ||
              proxyUrlQuery?.isLoading ||
              proxyEnabledMutation?.isLoading ||
              proxyEnabledQuery?.isLoading
            }
          >
            Update proxy URL
          </Button>
        </CardFooter>
      </Card>
    </form>
  );
}
