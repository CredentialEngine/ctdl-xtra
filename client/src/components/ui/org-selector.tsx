import { PropsWithChildren } from "react"
import { Button } from "./button"
import { ChevronRight, LucideBriefcaseBusiness } from "lucide-react";

export interface OrgSelectorProps {
  items: Array<{
    iconUrl?: string,
    key: React.Key,
    text: string,
    linkProps: {
      to: string
    }
  }>;
  density: keyof typeof DensityStyles;
  LinkComponent: React.FC<PropsWithChildren & { to: string, onClick: () => void }>;
  onSelected?: () => void
}

const DensityStyles = {
  relaxed: 'm-2 max-h-[50vh] p-2',
  dense: 'm-1 max-h-[30vh] p-2',
}

export function OrgSelector({ items, density, LinkComponent, onSelected }: OrgSelectorProps) {
  return (
    <div className={`${DensityStyles[density]} overflow-y-auto overflow-x-hidden flex flex-col items-center`}>
      {
        items.map(item =>
        (
          <Button
            asChild
            key={item?.key}
            className={`w-80 ${DensityStyles[density]} flex flex-row flex-no-wrap justify-between`}
            variant="outline"
          >
            <LinkComponent
              onClick={() => { typeof onSelected === 'function' && onSelected() }}
              {...item.linkProps}
            >
              {item.iconUrl
                ? <img src={item.iconUrl} />
                : <LucideBriefcaseBusiness />
              }
              <div className="overflow-hidden text-ellipsis max-w-[80%]">{item.text}</div>
              <ChevronRight />
            </LinkComponent>
          </Button>
        ))
      }
    </div>
  )
}