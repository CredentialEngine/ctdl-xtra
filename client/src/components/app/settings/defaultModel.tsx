import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import { ModelSelectGroups } from "@/components/app/ModelSelect";
import { coerceProviderModel, modelLabel } from "@common/modelMetadata";
import { ProviderModel } from "@common/types";
import { trpc } from "@/utils";
import { useEffect, useState } from "react";

export function DefaultExtractionModelForm() {
  const settingQuery = trpc.settings.detail.useQuery({
    key: "DEFAULT_EXTRACTION_MODEL",
  });
  const updateMutation = trpc.settings.setDefaultExtractionModel.useMutation();
  const [model, setModel] = useState<ProviderModel>(
    coerceProviderModel(settingQuery.data?.value)
  );
  const { toast } = useToast();

  useEffect(() => {
    if (settingQuery.data) {
      setModel(coerceProviderModel(settingQuery.data.value));
    }
  }, [settingQuery.data]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      await updateMutation.mutateAsync(model);
      toast({
        title: "Default Model Updated",
        description: "The default extraction model has been updated.",
      });
      settingQuery.refetch();
    } catch (error) {
      toast({
        title: "Error",
        description: "There was an error updating the default model.",
        variant: "destructive",
      });
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card className="flex-1 h-full w-[440px]">
        <CardHeader>
          <CardTitle>Default Extraction Model</CardTitle>
          <CardDescription>
            Model used when an extraction is started. A different model can
            still be chosen for a single run.
            {settingQuery.data?.value != null && (
              <span className="ml-1">
                (Current: {modelLabel(String(settingQuery.data.value))})
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="grid gap-2">
            <Label htmlFor="default_extraction_model">Model</Label>
            <Select
              value={model}
              onValueChange={(value) => setModel(value as ProviderModel)}
            >
              <SelectTrigger id="default_extraction_model" type="button">
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                <ModelSelectGroups />
              </SelectContent>
            </Select>
          </div>
        </CardContent>
        <CardFooter>
          <Button
            variant="outline"
            disabled={settingQuery.isLoading || updateMutation.isLoading}
          >
            Update
          </Button>
        </CardFooter>
      </Card>
    </form>
  );
}
