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
import { trpc } from "@/utils";
import { useEffect, useState } from "react";

export function MaxExtractionBudgetForm() {
  const settingQuery = trpc.settings.detail.useQuery({
    key: "MAX_EXTRACTION_BUDGET",
  });
  const updateMutation = trpc.settings.setMaxExtractionBudget.useMutation();
  const [budget, setBudget] = useState(
    settingQuery.data?.value !== undefined ? String(settingQuery.data.value) : ""
  );
  const { toast } = useToast();

  useEffect(() => {
    setBudget(
      settingQuery.data?.value !== undefined
        ? String(settingQuery.data.value)
        : ""
    );
  }, [settingQuery.data]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const parsed = parseFloat(budget);
    if (Number.isNaN(parsed) || parsed < 0) {
      toast({
        title: "Invalid budget",
        description: "Please enter a non-negative number.",
        variant: "destructive",
      });
      return;
    }
    try {
      await updateMutation.mutateAsync(parsed);
      toast({
        title: "Budget Updated",
        description: "Maximum extraction budget has been updated.",
      });
      // Keep the value entered; refetch to reflect server state
      settingQuery.refetch();
    } catch (error) {
      toast({
        title: "Error",
        description: "There was an error updating the budget.",
        variant: "destructive",
      });
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card className="flex-1 h-full w-[440px]">
        <CardHeader>
          <CardTitle>Max Extraction Budget</CardTitle>
          <CardDescription>
            Maximum USD budget allowed per extraction.
            {settingQuery.data?.value !== undefined ? (
              <span className="ml-1">(Current: ${settingQuery.data.value})</span>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="grid gap-2">
            <Label htmlFor="max_extraction_budget">New budget (USD)</Label>
            <Input
              id="max_extraction_budget"
              placeholder="e.g. 10.00"
              value={budget}
              onChange={(e) => { setBudget(e.target.value) }}
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
            />
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


