// Placeholder: the tour (spec §7.8) is built in wave 5. `useTour` decides when it opens; `Tour` renders it.
import { useCallback, useState } from "react";
import type { CatalogDetail } from "../api/types";

export function useTour(_catalog: CatalogDetail | null) {
  const [isOpen, setOpen] = useState(false);
  return { isOpen, open: useCallback(() => setOpen(true), []), close: useCallback(() => setOpen(false), []) };
}

export function Tour(_props: { isOpen: boolean; open: () => void; close: () => void; catalog: CatalogDetail }) {
  return null;
}
