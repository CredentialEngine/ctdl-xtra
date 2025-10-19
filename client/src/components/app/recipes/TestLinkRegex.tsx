import { useState, useEffect } from "react";
import {
  Card,
  CardHeader,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import { trpc } from "@/utils";

function MatchedLinks({
  result,
}: {
  result: { regexp: string; urls: string[] };
}) {
  return (
    <div className="mt-4">
      <div className="mb-2 text-xs text-muted-foreground">Tested RegExp:</div>
      <pre className="bg-muted/50 rounded p-2 text-xs overflow-x-auto mb-4">
        {result.regexp}
      </pre>
      <div className="mb-2 text-xs text-muted-foreground">Matching Links:</div>
      {result.urls.length > 0 ? (
        <ul className="text-xs max-h-40 overflow-y-auto space-y-1">
          {result.urls.map((link, i) => (
            <li key={i} className="truncate">
              {link}
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-xs text-muted-foreground">No links matched.</div>
      )}
    </div>
  );
}

export default function TestLinkRegex({
  defaultUrl,
  defaultRegex,
  simplified = false,
  clickSelector,
  clickOptions,
}: {
  defaultUrl: string;
  defaultRegex?: string;
  simplified?: boolean;
  clickSelector?: string;
  clickOptions?: { limit?: number; waitMs?: number };
}) {
  const [url, setUrl] = useState(defaultUrl);
  const [regex, setRegex] = useState(defaultRegex || "");
  const testRecipeRegex = trpc.recipes.testRecipeRegex.useMutation();

  useEffect(() => {
    setUrl(defaultUrl);
  }, [defaultUrl]);

  useEffect(() => {
    setRegex(defaultRegex || "");
  }, [defaultRegex]);

  const isDisabled = (!regex && !clickSelector) || testRecipeRegex.isLoading;

  // Simplified mode early return
  if (simplified) {
    return (
      <>
        <div className="flex space-x-4 mb-4">
          <Button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              const mutationData: {
                url: string;
                regex?: string;
                clickSelector?: string;
                clickOptions?: { limit?: number; waitMs?: number };
              } = {
                url,
              };
              
              if (regex && regex.trim()) {
                mutationData.regex = regex;
              }
              
              if (clickSelector !== undefined && clickSelector !== null) {
                mutationData.clickSelector = clickSelector;
              }
              
              if (clickOptions && (clickOptions.limit !== undefined || clickOptions.waitMs !== undefined)) {
                mutationData.clickOptions = clickOptions;
              }
              
              testRecipeRegex.mutate(mutationData);
            }}
            disabled={isDisabled}
          >
            {testRecipeRegex.isLoading && (
              <Loader2 className="animate-spin w-4 h-4 mr-2" />
            )}
            Test URL Detection
          </Button>
        </div>
        <div>
          {testRecipeRegex.isError && (
            <div className="text-sm text-red-600">
              {testRecipeRegex.error.message}
            </div>
          )}

          {testRecipeRegex.isSuccess && (
            <MatchedLinks result={testRecipeRegex.data} />
          )}
        </div>
      </>
    );
  }

  // Full mode
  return (
    <Card className="mt-4">
      <CardHeader>
        <CardDescription>Recipe Tester</CardDescription>
        <CardDescription>
          Enter a webpage URL and regex to test which links the recipe would
          extract.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4 mb-4">
          <div className="flex space-x-4">
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Page URL to test"
              className="flex-1"
              type="url"
            />
            <Input
              value={regex}
              onChange={(e) => setRegex(e.target.value)}
              placeholder="Regex pattern to test"
              className="flex-1"
            />
          </div>
        </div>
        <div className="flex space-x-4 mb-4">
          <Button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              const mutationData: {
                url: string;
                regex?: string;
                clickSelector?: string;
                clickOptions?: { limit?: number; waitMs?: number };
              } = {
                url,
              };
              
              if (regex && regex.trim()) {
                mutationData.regex = regex;
              }
              
              if (clickSelector !== undefined && clickSelector !== null) {
                mutationData.clickSelector = clickSelector;
              }
              
              if (clickOptions && (clickOptions.limit !== undefined || clickOptions.waitMs !== undefined)) {
                mutationData.clickOptions = clickOptions;
              }
              
              testRecipeRegex.mutate(mutationData);
            }}
            disabled={isDisabled}
          >
            {testRecipeRegex.isLoading && (
              <Loader2 className="animate-spin w-4 h-4 mr-2" />
            )}
            Test Regex
          </Button>
        </div>

        {testRecipeRegex.isError && (
          <div className="mt-2 text-red-600 text-sm">
            {testRecipeRegex.error.message}
          </div>
        )}

        {testRecipeRegex.isSuccess && (
          <MatchedLinks result={testRecipeRegex.data} />
        )}
      </CardContent>
    </Card>
  );
}
