import {
  SelectGroup,
  SelectItem,
  SelectLabel,
} from "@/components/ui/select";
import {
  PROVIDER_LABELS,
  modelsForProvider,
} from "@common/modelMetadata";
import { Provider } from "@common/types";

function formatReleaseDate(releaseDate: string) {
  return new Date(releaseDate).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function ModelSelectGroups() {
  return (
    <>
      {Object.values(Provider).map((provider) => (
        <SelectGroup key={provider}>
          <SelectLabel>{PROVIDER_LABELS[provider]}</SelectLabel>
          {modelsForProvider(provider).map((meta) => (
            <SelectItem
              key={meta.model}
              value={meta.model}
              className="cursor-pointer"
            >
              {meta.label}
              {meta.isCheapest ? " (Lowest cost)" : ""}
              {meta.bestValue ? " (Best Value)" : ""}
              {meta.isFlagship ? " (Flagship)" : ""}
              {meta.hint ? ` (${meta.hint})` : ""}
              <span className="opacity-60">
                {" — "}
                {formatReleaseDate(meta.releaseDate)}
              </span>
            </SelectItem>
          ))}
        </SelectGroup>
      ))}
    </>
  );
}
