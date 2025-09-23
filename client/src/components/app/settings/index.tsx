import { OpenAIApiKeyForm } from "./openapi";
import { ProxySettingsForm } from "./proxy";
import { MaxExtractionBudgetForm } from "./budget";

export default function Settings() {
  return (
    <>
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Settings</h1>
      </div>
      <div className="flex gap-4 min-h-0 w-full shadow-sm flex-wrap">
        <OpenAIApiKeyForm />
        <ProxySettingsForm />
        <MaxExtractionBudgetForm />
      </div>
    </>
  );
}
