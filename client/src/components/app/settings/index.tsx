import { OpenAIApiKeyForm } from "./openapi";
import { ProxySettingsForm } from "./proxy";

export default function Settings() {
  return (
    <>
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Settings</h1>
      </div>
      <div className="flex gap-4 min-h-0 shadow-sm">
        <OpenAIApiKeyForm />
        <ProxySettingsForm />
      </div>
    </>
  );
}
