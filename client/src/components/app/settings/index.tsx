import { trpc } from "@/utils";
import { OpenAIApiKeyForm } from "./openapi";
import { CrawlerSettingsForm } from "./crawler";

export default function Settings() {
  const listQuery = trpc.settings.list.useQuery();

  const openAIApiKey = listQuery.data?.find(
    (setting) => setting.key === "OPENAI_API_KEY"
  );

  return (
    <>
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Settings</h1>
      </div>
      <div className="flex gap-4 min-h-0 shadow-sm">
        <OpenAIApiKeyForm
          currentApiKeyPreview={openAIApiKey?.encryptedPreview}
          onSuccess={listQuery.refetch}
        />
        <CrawlerSettingsForm
          settingsQuery={listQuery}
          onSuccess={listQuery.refetch}
        />
      </div>
    </>
  );
}
