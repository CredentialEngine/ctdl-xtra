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
import { useCallback, useEffect, useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";

type SettingsList = RouterOutput['settings']['list'];
type SettingsListQuery = UseTRPCQueryResult<SettingsList, TRPCClientErrorLike<AppRouter>>;

interface CrawlerSettingsFormProps {
  settingsQuery: SettingsListQuery;
  onSuccess: () => void;
}

const SupportedCrawlers = [
  { value: "FireCrawler", label: "FireCrawler" },
  { value: "OxyLabs", label: "OxyLabs" },
  { value: "BrightData", label: "BrightData" },
  { value: "SmartProxy", label: "SmartProxy" },
] as const;

const redacted = "*****"

export function CrawlerSettingsForm({
  settingsQuery,
  onSuccess,
}: CrawlerSettingsFormProps) {
  const updateMutation = trpc.settings.setSetting.useMutation();
  const dbSetting = settingsQuery?.data?.find((setting) => setting.key === 'CRAWLER');
  const dbSettingRawValue = settingsQuery?.data?.find((setting) => setting.key === 'CRAWLER')?.encryptedPreview;
  const dbSettingValue = dbSettingRawValue ? JSON.parse(dbSettingRawValue) : null;
  const [apiKey, setApiKey] = useState("");
  const [selectedType, setSelectedType] = useState<string>(SupportedCrawlers[0].value);
  const [isEnabled, setIsEnabled] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    if (dbSettingValue) {
      setIsEnabled(dbSettingValue?.isEnabled);
      setSelectedType(dbSettingValue.activeCrawler || SupportedCrawlers[0].value);
      setApiKey(dbSettingValue[dbSettingValue.activeCrawler]?.apiKey || "");
    }
  }, [dbSettingRawValue]);

  const onSelectTypeChange = useCallback((newValue: string) => {
    setSelectedType(newValue);
    setApiKey(dbSettingValue[newValue]?.apiKey || "");
  }, [dbSettingValue]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      const newValue = {
        isEnabled,
        activeCrawler: selectedType,
        [selectedType]: { apiKey },
      }

      let encryptedPreview;
      try {
        encryptedPreview = JSON.parse(dbSetting?.encryptedPreview || "{}");
      } catch (error) {
        encryptedPreview = null;
      }

      encryptedPreview = {
        ...encryptedPreview,
        activeCrawler: selectedType,
        [selectedType]: { apiKey: redacted },
        isEnabled,
      }
      
      await updateMutation.mutateAsync({
        key: 'CRAWLER',
        value: JSON.stringify(newValue),
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
          <CardTitle>Crawler Proxy</CardTitle>
          <CardDescription>
            Activating a crawler proxy is helpful in overcoming rate limits or <br />
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
            <Label htmlFor="enabled">Enable Crawler Proxy</Label>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="active_crawler">Active Crawler</Label>
            <Select disabled={settingsQuery?.isLoading} value={selectedType} onValueChange={onSelectTypeChange}>
              <SelectTrigger>
                <SelectValue placeholder="Select a crawler" />
              </SelectTrigger>
              <SelectContent>
                {SupportedCrawlers.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="api_key">{selectedType} API Key</Label>
            <Input
              id="api_key"
              placeholder="Enter API key..."
              disabled={settingsQuery?.isLoading}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              type="text"
            />
          </div>
        </CardContent>
        <CardFooter>
          <Button variant="outline" disabled={updateMutation?.isLoading || settingsQuery?.isLoading || apiKey === redacted}>Update</Button>
        </CardFooter>
      </Card>
    </form>
  );
}
