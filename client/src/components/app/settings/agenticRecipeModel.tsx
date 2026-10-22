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
import { coerceAnthropicModel, modelLabel } from "@common/modelMetadata";
import { Provider, ProviderModel } from "@common/types";
import { trpc } from "@/utils";
import { useEffect, useState } from "react";

export function AgenticRecipeModelForm() {
  const settingQuery = trpc.settings.detail.useQuery({
    key: "AGENTIC_RECIPE_MODEL",
  });
  const updateMutation = trpc.settings.setAgenticRecipeModel.useMutation();
  const [model, setModel] = useState<ProviderModel>(
    coerceAnthropicModel(settingQuery.data?.value)
  );
  const { toast } = useToast();

  useEffect(() => {
    if (settingQuery.data) {
      setModel(coerceAnthropicModel(settingQuery.data.value));
    }
  }, [settingQuery.data]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      await updateMutation.mutateAsync(model);
      toast({
        title: "Agentic Recipe Model Updated",
        description:
          "The model used for agentic recipe setup has been updated.",
      });
      settingQuery.refetch();
    } catch (error) {
      toast({
        title: "Error",
        description: "There was an error updating the agentic recipe model.",
        variant: "destructive",
      });
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card className="flex-1 h-full w-[440px]">
        <CardHeader>
          <CardTitle>Agentic Recipe Model</CardTitle>
          <CardDescription>
            Claude model used when a recipe is configured with the agentic
            workflow.
            {settingQuery.data?.value != null && (
              <span className="ml-1">
                (Current: {modelLabel(String(settingQuery.data.value))})
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="grid gap-2">
            <Label htmlFor="agentic_recipe_model">Model</Label>
            <Select
              value={model}
              onValueChange={(value) => setModel(value as ProviderModel)}
            >
              <SelectTrigger id="agentic_recipe_model" type="button">
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                <ModelSelectGroups provider={Provider.Anthropic} />
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
