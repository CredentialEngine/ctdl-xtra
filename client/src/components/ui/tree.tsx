import * as React from "react";
import { ChevronRight, File, Eye } from "lucide-react";
import { cn } from "@/utils";

export interface TreeNode {
  id: string | number;
  label: string;
  children?: TreeNode[];
  [key: string]: any;
}

interface TreeProps {
  data: TreeNode[];
  className?: string;
  defaultExpanded?: boolean;
  onNodeClick?: (node: TreeNode) => void;
}

interface TreeNodeProps {
  node: TreeNode;
  level: number;
  defaultExpanded?: boolean;
  onNodeClick?: (node: TreeNode) => void;
}

const TreeNodeComponent: React.FC<TreeNodeProps> = ({
  node,
  level,
  defaultExpanded = false,
  onNodeClick,
}) => {
  const [isExpanded, setIsExpanded] = React.useState(defaultExpanded);
  const hasChildren = node.children && node.children.length > 0;

  const handleToggle = () => {
    if (hasChildren) {
      setIsExpanded(!isExpanded);
    }
  };

  const handleViewClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onNodeClick) {
      onNodeClick(node);
    }
  };

  const isPage = node.type === 'page';
  const showExpandIcon = hasChildren && !isPage;
  const canView = (node.type === 'page' && node.page) || (node.type === 'step' && node.step);

  return (
    <div className="select-none">
      <div
        className="flex items-center gap-1 py-1 px-2 rounded-sm hover:bg-accent group cursor-pointer"
        style={{ paddingLeft: `${level * 1.5}rem` }}
        onClick={hasChildren ? handleToggle : undefined}
      >
        <div
          className={cn(
            "flex items-center justify-center w-4 h-4",
            !showExpandIcon && !isPage && "invisible"
          )}
          onClick={(e) => {
            e.stopPropagation();
            if (showExpandIcon) {
              handleToggle();
            }
          }}
        >
          {isPage ? (
            <File className="h-3.5 w-3.5 text-muted-foreground" />
          ) : showExpandIcon ? (
            <ChevronRight
              className={cn(
                "h-4 w-4 transition-transform cursor-pointer",
                isExpanded && "transform rotate-90"
              )}
            />
          ) : null}
        </div>
        <div className="flex-1 flex flex-col">
          <span className="text-sm">{node.label}</span>
          {node.url && node.type !== 'page' && (
            <span className="text-xs text-muted-foreground truncate" title={node.url}>
              {node.url}
            </span>
          )}
        </div>
        {canView && (
          <button
            onClick={handleViewClick}
            className={cn(
              "opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-accent-foreground/10 rounded",
              "flex items-center justify-center"
            )}
            title="View details"
          >
            <Eye className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        )}
      </div>
      {hasChildren && isExpanded && (
        <div>
          {node.children!.map((child) => (
            <TreeNodeComponent
              key={child.id}
              node={child}
              level={level + 1}
              defaultExpanded={defaultExpanded}
              onNodeClick={onNodeClick}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const Tree: React.FC<TreeProps> = ({
  data,
  className,
  defaultExpanded = false,
  onNodeClick,
}) => {
  return (
    <div className={cn("rounded-md border p-2", className)}>
      {data.map((node) => (
        <TreeNodeComponent
          key={node.id}
          node={node}
          level={0}
          defaultExpanded={defaultExpanded}
          onNodeClick={onNodeClick}
        />
      ))}
    </div>
  );
};

