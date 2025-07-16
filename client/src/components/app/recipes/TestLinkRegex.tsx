import { useState } from "react";
import { Card, CardHeader, CardDescription, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import { trpc } from "@/utils";

export default function TestLinkRegex({
  defaultUrl,
  defaultRegex,
}: {
  defaultUrl: string;
  defaultRegex?: string;
}) {
  const [url, setUrl] = useState(defaultUrl);
  const [regex, setRegex] = useState(defaultRegex || "");
  const testRecipeRegex = trpc.recipes.testRecipeRegex.useMutation();

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardDescription>Recipe Tester</CardDescription>
        <CardDescription>Enter a webpage URL to test if this recipe can find the right links on that page. The test will show you which links the recipe would extract, helping you verify it's working correctly before running a full extraction.</CardDescription>
      </CardHeader>
      <CardContent>
          <div className="space-y-4">
            <div className="flex space-x-4">
            <Input
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="Page URL to test"
              className="flex-1"
              type="url"
            />
              <Input
                value={regex}
                onChange={e => setRegex(e.target.value)}
                placeholder="Regex pattern to test"
                className="flex-1"
              />
            </div>
            <div className="flex space-x-4">
            <Button 
              onClick={(e) => {
                e.preventDefault();
                testRecipeRegex.mutate({ url, regex });
              }}
              disabled={testRecipeRegex.isLoading}
            >
              {testRecipeRegex.isLoading ? <Loader2 className="animate-spin w-4 h-4 mr-2" /> : null}
              Test
            </Button>
            </div>
          </div>
        {testRecipeRegex.isError && (
          <div className="mt-4 text-red-600 text-sm">{testRecipeRegex.error.message}</div>
        )}
        {testRecipeRegex.isSuccess && (
          <div className="mt-4">
            <div className="mb-2 text-xs text-muted-foreground">Tested RegExp:</div>
            <pre className="bg-muted/50 rounded p-2 text-xs overflow-x-auto mb-4">{testRecipeRegex.data.regexp}</pre>
            <div className="mb-2 text-xs text-muted-foreground">Matching Links:</div>
            {testRecipeRegex.data.urls.length > 0 ? (
              <ul className="text-xs max-h-40 overflow-y-auto space-y-1">
                {testRecipeRegex.data.urls.map((link, i) => (
                  <li key={i} className="truncate">{link}</li>
                ))}
              </ul>
            ) : (
              <div className="text-xs text-muted-foreground">No links matched.</div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
} 