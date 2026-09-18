"use client";

import {
    FormControl,
    InputLabel,
    MenuItem,
    Select as MuiSelect,
    type SelectChangeEvent,
} from "@mui/material";
import React from "react";

type Item = { value: string; label: React.ReactNode; disabled?: boolean };
type SelectContextValue = {
    value: string;
    setValue: (value: string) => void;
    disabled?: boolean;
    items: Item[];
};

type SelectProps = {
    value?: string;
    defaultValue?: string;
    onValueChange?: (value: string) => void;
    disabled?: boolean;
    children: React.ReactNode;
};

type SelectTriggerProps = React.ComponentPropsWithoutRef<typeof FormControl> & {
    children: React.ReactNode;
    id?: string;
    "aria-label"?: string;
    "aria-describedby"?: string;
};

type SelectItemProps = {
    value: string;
    disabled?: boolean;
    children: React.ReactNode;
};

const SelectCtx = React.createContext<SelectContextValue | null>(null);

function collectItems(children: React.ReactNode): Item[] {
    const items: Item[] = [];

    function walk(node: React.ReactNode) {
        React.Children.forEach(node, (child) => {
            if (!React.isValidElement(child)) return;
            const displayName = (child.type as { displayName?: string })
                ?.displayName;
            if (displayName === "SelectItem") {
                const props = child.props as SelectItemProps;
                items.push({
                    value: props.value,
                    label: props.children,
                    disabled: props.disabled,
                });
                return;
            }
            const props = child.props as { children?: React.ReactNode };
            if (props.children) walk(props.children);
        });
    }

    walk(children);
    return items;
}

function Select({
    value,
    defaultValue = "",
    onValueChange,
    disabled,
    children,
}: SelectProps) {
    const [internal, setInternal] = React.useState(defaultValue);
    const current = value ?? internal;
    const items = React.useMemo(() => collectItems(children), [children]);
    const setValue = React.useCallback(
        (next: string) => {
            if (value === undefined) setInternal(next);
            onValueChange?.(next);
        },
        [onValueChange, value],
    );

    return (
        <SelectCtx.Provider
            value={{ value: current, setValue, disabled, items }}
        >
            {children}
        </SelectCtx.Provider>
    );
}

function SelectValue({ placeholder }: { placeholder?: React.ReactNode }) {
    void placeholder;
    return null;
}
SelectValue.displayName = "SelectValue";

const SelectTrigger = React.forwardRef<HTMLDivElement, SelectTriggerProps>(
    function SelectTrigger(
        {
            children,
            className,
            id,
            "aria-label": ariaLabel,
            "aria-describedby": ariaDescribedBy,
            ...props
        },
        ref,
    ) {
        const ctx = React.useContext(SelectCtx);
        const generatedId = React.useId();
        if (!ctx) throw new Error("SelectTrigger must be used inside Select");

        let placeholder: React.ReactNode;
        React.Children.forEach(children, (child) => {
            if (
                React.isValidElement(child) &&
                (child.type as { displayName?: string })?.displayName ===
                    "SelectValue"
            ) {
                placeholder = (child.props as { placeholder?: React.ReactNode })
                    .placeholder;
            }
        });

        const handleChange = (event: SelectChangeEvent<string>) =>
            ctx.setValue(event.target.value);
        const selectedItem = ctx.items.find((item) => item.value === ctx.value);
        const safeValue = ctx.items.some((item) => item.value === ctx.value)
            ? ctx.value
            : "";
        const selectId = id ?? `select-${generatedId}`;
        const labelId = `${selectId}-label`;

        return (
            <FormControl
                ref={ref}
                size="small"
                disabled={ctx.disabled}
                className={className}
                fullWidth
                {...props}
            >
                {placeholder ? (
                    <InputLabel
                        id={labelId}
                        htmlFor={selectId}
                        shrink={Boolean(safeValue)}
                    >
                        {placeholder}
                    </InputLabel>
                ) : null}
                <MuiSelect
                    id={selectId}
                    labelId={placeholder ? labelId : undefined}
                    value={safeValue}
                    onChange={handleChange}
                    label={placeholder}
                    displayEmpty
                    inputProps={{
                        "aria-label":
                            ariaLabel ||
                            (!placeholder ? "Select an option" : undefined),
                        "aria-describedby": ariaDescribedBy,
                    }}
                    renderValue={(selected) =>
                        selectedItem?.label ??
                        (selected ? (
                            String(selected)
                        ) : (
                            <span style={{ opacity: 0.7 }}>{placeholder}</span>
                        ))
                    }
                >
                    {ctx.items.map((item) => (
                        <MenuItem
                            key={item.value}
                            value={item.value}
                            disabled={item.disabled}
                        >
                            {item.label}
                        </MenuItem>
                    ))}
                </MuiSelect>
            </FormControl>
        );
    },
);

function SelectContent({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
}
SelectContent.displayName = "SelectContent";

function SelectItem(props: SelectItemProps) {
    void props;
    return null;
}
SelectItem.displayName = "SelectItem";

export { Select, SelectValue, SelectTrigger, SelectContent, SelectItem };
