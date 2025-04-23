import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { AppRouter, RouterOutput, trpc } from "@/utils";
import { TRPCClientErrorLike } from "@trpc/react-query";
import { UseTRPCQueryResult } from "@trpc/react-query/shared";
import { useEffect, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
type SettingsList = RouterOutput['settings']['list'];
type SettingsListQuery = UseTRPCQueryResult<SettingsList, TRPCClientErrorLike<AppRouter>>;

interface ProxySettingsFormProps {
  settingsQuery: SettingsListQuery;
  onSuccess: () => void;
}

const redacted = "*****"

export function ProxySettingsForm({
  settingsQuery,
  onSuccess,
}: ProxySettingsFormProps) {
  const updateMutation = trpc.settings.setSetting.useMutation();
  const dbSetting = settingsQuery?.data?.find((setting) => setting.key === 'PROXY');
  const dbSettingRawValue = settingsQuery?.data?.find((setting) => setting.key === 'PROXY')?.encryptedPreview;
  const dbSettingValue = dbSettingRawValue ? JSON.parse(dbSettingRawValue) : null;
  const [proxyUrl, setProxyUrl] = useState("");
  const [isEnabled, setIsEnabled] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    if (dbSettingValue) {
      setIsEnabled(dbSettingValue?.enabled);
      setProxyUrl(dbSettingValue?.url || "");
    }
  }, [dbSettingRawValue]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      const newValue: Partial<{ enabled: boolean, url: string }> = {
        enabled: isEnabled
      }

      if (proxyUrl !== redacted) {
        newValue.url = proxyUrl;
      }

      let encryptedPreview;
      try {
        encryptedPreview = JSON.parse(dbSetting?.encryptedPreview || "{}");
      } catch (error) {
        encryptedPreview = null;
      }

      encryptedPreview = {
        ...encryptedPreview,
        url: redacted,
        enabled: isEnabled,
      }
      
      await updateMutation.mutateAsync({
        key: 'PROXY',
        value: newValue as any,
        isEncrypted: true,
        merge: true,
        encryptedPreview: JSON.stringify(encryptedPreview),
      });
      toast({
        title: "Settings Updated",
        description: "The setting has been updated successfully.",
      });
      onSuccess();
    } catch (error) {
      toast({
        title: "Error",
        description: "There was an error updating the setting.",
        variant: "destructive",
      });
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card className="flex-1">
        <CardHeader>
          <CardTitle>Proxy Settings</CardTitle>
          <CardDescription>
            Activating a proxy is helpful in overcoming rate limits or <br />
            blocking by anti-scraping measures. <br />
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="flex items-center space-x-2">
            <Checkbox
              id="enabled"
              disabled={settingsQuery?.isLoading}
              checked={isEnabled}
              onCheckedChange={(checked) => setIsEnabled(checked as boolean)}
            />
            <Label htmlFor="enabled">Enable Proxy</Label>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="proxy_url">Proxy URL</Label>
            <Input
              id="proxy_url"
              placeholder="https://username:password@proxy.com:port"
              disabled={settingsQuery?.isLoading}
              value={proxyUrl}
              onChange={(e) => setProxyUrl(e.target.value)}
              type="text"
            />
          </div>
        </CardContent>
        <CardFooter>
          <Button variant="outline" disabled={updateMutation?.isLoading || settingsQuery?.isLoading}>Update</Button>
        </CardFooter>
      </Card>
    </form>
  );
}
