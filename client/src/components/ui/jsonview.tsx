import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import React, { useState } from "react";

export function cn(...inputs: (string | undefined | null | false | 0)[]) {
  return inputs.filter(Boolean).join(" ");
}

interface JsonViewProps {
  data: any;
  initialExpanded?: boolean;
  className?: string;
}

const JsonView: React.FC<JsonViewProps> = ({
  data,
  initialExpanded = false,
  className,
}) => {
  return (
    <div className={cn("font-mono text-sm overflow-auto", className)}>
      <JsonNode
        data={data}
        name="root"
        initialExpanded={initialExpanded}
        level={0}
      />
    </div>
  );
};

interface JsonNodeProps {
  data: any;
  name: string;
  initialExpanded?: boolean;
  level: number;
  isLast?: boolean;
}

const JsonNode: React.FC<JsonNodeProps> = ({
  data,
  name,
  initialExpanded = false,
  level,
  isLast = true,
}) => {
  const [isExpanded, setIsExpanded] = useState(initialExpanded);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getType = (value: any): string => {
    if (value === null) return "null";
    if (Array.isArray(value)) return "array";
    return typeof value;
  };

  const type = getType(data);
  const isExpandable = type === "object" || type === "array";
  const isEmpty = isExpandable && Object.keys(data).length === 0;

  const renderValue = () => {
    switch (type) {
      case "string":
        return <span className="text-green-600">"{data}"</span>;
      case "number":
        return <span className="text-blue-600">{data}</span>;
      case "boolean":
        return <span className="text-purple-600">{data.toString()}</span>;
      case "null":
        return <span className="text-gray-500">null</span>;
      case "undefined":
        return <span className="text-gray-500">undefined</span>;
      case "object":
        return isEmpty ? <span className="text-gray-500">{"{}"}</span> : null;
      case "array":
        return isEmpty ? <span className="text-gray-500">[]</span> : null;
      default:
        return <span>{String(data)}</span>;
    }
  };

  const renderChildren = () => {
    if (!isExpandable || !isExpanded) return null;

    const entries = Object.entries(data);
    return (
      <div className="ml-6">
        {entries.map(([key, value], index) => (
          <JsonNode
            key={key}
            data={value}
            name={type === "array" ? index.toString() : key}
            initialExpanded={initialExpanded}
            level={level + 1}
            isLast={index === entries.length - 1}
          />
        ))}
      </div>
    );
  };

  if (name === "root" && level === 0) {
    if (isExpandable) {
      return renderChildren();
    } else {
      return renderValue();
    }
  }

  return (
    <div className="my-1">
      <div className="flex items-start">
        {isExpandable ? (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="mr-1 p-0.5 hover:bg-gray-200 rounded"
          >
            {isExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </button>
        ) : (
          <span className="w-4" />
        )}

        <div className="flex-1">
          <span className="text-gray-800">
            {type === "array" ? `[${name}]` : name}
          </span>
          <span className="mx-1 text-gray-500">:</span>

          {isExpandable && !isEmpty ? (
            <span className="text-gray-500">
              {isExpanded ? (
                type === "array" ? (
                  "["
                ) : (
                  "{"
                )
              ) : (
                <span
                  onClick={() => setIsExpanded(true)}
                  className="cursor-pointer"
                >
                  {type === "array"
                    ? `[...${Object.keys(data).length} items]`
                    : `{...${Object.keys(data).length} properties}`}
                </span>
              )}
            </span>
          ) : (
            renderValue()
          )}

          {!isLast && <span className="text-gray-500">,</span>}

          {level === 1 && (
            <button
              onClick={handleCopy}
              className="ml-2 p-0.5 hover:bg-gray-200 rounded opacity-50 hover:opacity-100"
              title="Copy to clipboard"
            >
              <Copy className="h-3 w-3" />
              {copied && (
                <span className="ml-1 text-xs text-green-600">Copied!</span>
              )}
            </button>
          )}
        </div>
      </div>

      {isExpanded && renderChildren()}

      {isExpandable && isExpanded && !isEmpty && (
        <div className={cn("text-gray-500", level > 0 ? "ml-6" : "")}>
          {type === "array" ? "]" : "}"}
          {!isLast && ","}
        </div>
      )}
    </div>
  );
};

export { JsonView };
