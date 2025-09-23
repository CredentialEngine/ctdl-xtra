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
import { useState } from "react";

export function OpenAIApiKeyForm() {
  const settingQuery = trpc.settings.detail.useQuery({
    key: "OPENAI_API_KEY",
  });
  const updateMutation = trpc.settings.setOpenAIApiKey.useMutation();
  const [apiKey, setApiKey] = useState("");
  const { toast } = useToast();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    try {
      await updateMutation.mutateAsync({ apiKey: apiKey });
      toast({
        title: "API Key Updated",
        description: "The OpenAI API key has been updated.",
      });
      setApiKey("");
      settingQuery.refetch();
    } catch (error) {
      toast({
        title: "Error",
        description: "There was an error updating the API key.",
      });
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card className="flex-1 h-full w-[440px]">
        <CardHeader>
          <CardTitle>OpenAI API Key</CardTitle>
          <CardDescription>
            The API key that will used for OpenAI requests. <br />
            {settingQuery.data?.encryptedPreview ? (
              <>
                The key is currently set to{" "}
                <code className="font-bold">
                  {settingQuery.data.encryptedPreview}
                </code>
                .
              </>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="grid gap-2">
            <Label htmlFor="openai_api_key">New key</Label>
            <Input
              id="openai_api_key"
              placeholder="sk-..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              type="password"
            />
          </div>
        </CardContent>
        <CardFooter>
          <Button variant="outline">Update</Button>
        </CardFooter>
      </Card>
    </form>
  );
}
