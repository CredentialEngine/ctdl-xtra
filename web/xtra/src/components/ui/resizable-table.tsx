"use client";

import {
    Button,
    Checkbox,
    Popover,
    Table as AntTable,
    type TableProps,
} from "antd";
import type { ColumnType, ColumnsType } from "antd/es/table";
import React, { useEffect, useMemo, useRef, useState } from "react";

const MIN_COLUMN_WIDTH = 72;
const DEFAULT_COLUMN_WIDTH = 160;
const MAX_COLUMN_WIDTH = 720;

type ResizeHeaderCellProps = React.ThHTMLAttributes<HTMLTableCellElement> & {
    width?: number;
    columnKey?: React.Key;
    onColumnResize?: (key: React.Key, width: number) => void;
    columnLabel?: string;
};

function ResizeHeaderCell({
    width,
    columnKey,
    onColumnResize,
    columnLabel,
    children,
    style,
    ...rest
}: ResizeHeaderCellProps) {
    const currentWidth = width ?? DEFAULT_COLUMN_WIDTH;

    const resizeTo = (nextWidth: number) => {
        if (columnKey == null || !onColumnResize) return;
        onColumnResize(
            columnKey,
            Math.min(MAX_COLUMN_WIDTH, Math.max(MIN_COLUMN_WIDTH, nextWidth)),
        );
    };

    const startPointerResize = (event: React.PointerEvent<HTMLSpanElement>) => {
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const startWidth = currentWidth;
        const target = event.currentTarget;
        target.setPointerCapture(event.pointerId);

        const onMove = (moveEvent: PointerEvent) =>
            resizeTo(startWidth + moveEvent.clientX - startX);
        const onUp = (upEvent: PointerEvent) => {
            target.releasePointerCapture(upEvent.pointerId);
            target.removeEventListener("pointermove", onMove);
            target.removeEventListener("pointerup", onUp);
            target.removeEventListener("pointercancel", onUp);
        };

        target.addEventListener("pointermove", onMove);
        target.addEventListener("pointerup", onUp);
        target.addEventListener("pointercancel", onUp);
    };

    return (
        <th
            {...rest}
            style={{
                ...style,
                width: width ?? style?.width,
                position: "relative",
            }}
        >
            {children}
            {columnKey != null && onColumnResize && (
                <span
                    role="separator"
                    aria-orientation="vertical"
                    aria-label={`Resize ${columnLabel ?? String(columnKey)} column`}
                    aria-valuemin={MIN_COLUMN_WIDTH}
                    aria-valuemax={MAX_COLUMN_WIDTH}
                    aria-valuenow={currentWidth}
                    tabIndex={0}
                    onPointerDown={startPointerResize}
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => {
                        if (event.key === "ArrowLeft") {
                            event.preventDefault();
                            event.stopPropagation();
                            resizeTo(currentWidth - 16);
                        } else if (event.key === "ArrowRight") {
                            event.preventDefault();
                            event.stopPropagation();
                            resizeTo(currentWidth + 16);
                        } else if (event.key === "Home") {
                            event.preventDefault();
                            resizeTo(MIN_COLUMN_WIDTH);
                        } else if (event.key === "End") {
                            event.preventDefault();
                            resizeTo(MAX_COLUMN_WIDTH);
                        }
                    }}
                    className="ant-column-resize-handle"
                />
            )}
        </th>
    );
}

export type ResizableTableProps<RecordType extends object> =
    TableProps<RecordType> & {
        ariaLabel: string;
    };

function getColumnKey<RecordType extends object>(
    column: ColumnType<RecordType>,
    index: number,
) {
    return String(
        column.key ??
            ("dataIndex" in column ? (column.dataIndex ?? index) : index),
    );
}

function getColumnLabel<RecordType extends object>(
    column: ColumnType<RecordType>,
    index: number,
) {
    if (typeof column.title === "string" && column.title.trim())
        return column.title;
    return `Column ${index + 1}`;
}

/**
 * Shared Ant table with multi-column sort/filter support, resizable columns,
 * and a consistent column visibility control for every table in the app.
 * Ant Table does not ship a built-in column chooser, so this wrapper provides
 * one centrally instead of reimplementing it on each page.
 */
export default function ResizableTable<RecordType extends object>({
    columns = [],
    ariaLabel,
    scroll,
    ...props
}: ResizableTableProps<RecordType>) {
    const typedColumns = columns as ColumnsType<RecordType>;
    const initialHidden = useMemo(() => {
        const hidden = new Set<string>();
        typedColumns.forEach((column, index) => {
            if (
                (column as ColumnType<RecordType> & { hidden?: boolean }).hidden
            )
                hidden.add(
                    getColumnKey(column as ColumnType<RecordType>, index),
                );
        });
        return hidden;
        // Column definitions are intentionally treated as initial visibility metadata.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const [hiddenColumns, setHiddenColumns] =
        useState<Set<string>>(initialHidden);
    const [widths, setWidths] = useState<Record<string, number>>({});
    const [hasUserResized, setHasUserResized] = useState(false);
    const [availableWidth, setAvailableWidth] = useState(0);
    const regionRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const region = regionRef.current;
        if (!region) return;
        const observer = new ResizeObserver((entries) => {
            const width = entries[0]?.contentRect.width ?? 0;
            setAvailableWidth(width);
        });
        observer.observe(region);
        return () => observer.disconnect();
    }, []);

    const updateWidth = (key: React.Key, width: number) => {
        setHasUserResized(true);
        setWidths((current) => ({ ...current, [String(key)]: width }));
    };

    const allColumnOptions = useMemo(
        () =>
            typedColumns.map((column, index) => ({
                key: getColumnKey(column as ColumnType<RecordType>, index),
                label: getColumnLabel(column as ColumnType<RecordType>, index),
            })),
        [typedColumns],
    );

    const resizableColumns = useMemo<ColumnsType<RecordType>>(
        () =>
            typedColumns
                .map((column, index) => ({
                    column: column as ColumnType<RecordType>,
                    index,
                }))
                .filter(
                    ({ column, index }) =>
                        !hiddenColumns.has(getColumnKey(column, index)),
                )
                .map(({ column, index }) => {
                    const columnKey = getColumnKey(column, index);
                    const declaredWidth =
                        typeof column.width === "number"
                            ? column.width
                            : undefined;
                    const width = widths[columnKey] ?? declaredWidth;
                    const visibleColumn = {
                        ...column,
                    } as ColumnType<RecordType> & { hidden?: boolean };
                    delete visibleColumn.hidden;
                    return {
                        ...visibleColumn,
                        width,
                        onHeaderCell: () =>
                            ({
                                width: width ?? DEFAULT_COLUMN_WIDTH,
                                columnKey,
                                onColumnResize: updateWidth,
                                columnLabel: getColumnLabel(column, index),
                            }) as React.HTMLAttributes<HTMLTableCellElement>,
                    } as ColumnType<RecordType>;
                }),
        [typedColumns, hiddenColumns, widths],
    );

    const preferredTotalWidth = resizableColumns.reduce(
        (sum, column) =>
            sum +
            (typeof column.width === "number"
                ? column.width
                : DEFAULT_COLUMN_WIDTH),
        0,
    );
    const userScrollX = typeof scroll?.x === "number" ? scroll.x : 0;
    const needsUserScroll =
        hasUserResized &&
        availableWidth > 0 &&
        preferredTotalWidth > availableWidth;
    const effectiveScroll = needsUserScroll
        ? {
              ...scroll,
              x: Math.max(preferredTotalWidth, userScrollX, availableWidth),
          }
        : scroll?.y
          ? { y: scroll.y }
          : undefined;

    const columnChooser = (
        <div
            className="min-w-52 space-y-1 p-1"
            role="group"
            aria-label={`Visible columns for ${ariaLabel}`}
        >
            {allColumnOptions.map((option) => {
                const checked = !hiddenColumns.has(option.key);
                const visibleCount =
                    allColumnOptions.length - hiddenColumns.size;
                return (
                    <label
                        key={option.key}
                        className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-[var(--ce-surface)]"
                    >
                        <Checkbox
                            checked={checked}
                            disabled={checked && visibleCount === 1}
                            onChange={(event) => {
                                setHiddenColumns((current) => {
                                    const next = new Set(current);
                                    if (event.target.checked)
                                        next.delete(option.key);
                                    else next.add(option.key);
                                    return next;
                                });
                            }}
                        />
                        <span>{option.label}</span>
                    </label>
                );
            })}
        </div>
    );

    return (
        <div
            ref={regionRef}
            role="region"
            aria-label={ariaLabel}
            className="min-w-0"
        >
            <div className="mb-2 flex justify-end">
                <Popover
                    placement="bottomRight"
                    trigger="click"
                    content={columnChooser}
                    title="Show / hide columns"
                >
                    <Button
                        size="small"
                        aria-label={`Show or hide columns in ${ariaLabel}`}
                    >
                        Columns
                    </Button>
                </Popover>
            </div>
            <AntTable<RecordType>
                {...props}
                columns={resizableColumns}
                components={{ header: { cell: ResizeHeaderCell } }}
                scroll={effectiveScroll}
                tableLayout="auto"
            />
        </div>
    );
}
