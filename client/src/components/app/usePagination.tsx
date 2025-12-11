import { useState } from "react";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "../ui/pagination";

export interface PaginationOutput {
  totalItems: number;
  totalPages: number;
  results: any[];
}

export interface PaginationButtonsProps {
  totalItems: number;
  totalPages: number;
}

export default function usePagination() {
  const [page, setPage] = useState(1);

  const PaginationButtons = ({
    totalItems,
    totalPages,
  }: PaginationButtonsProps) => {
    const firstPageItem = (page - 1) * 20 + 1;
    const lastPageItem = page === totalPages ? totalItems : page * 20;

    const changePage = (newPage: number) => {
      if (newPage >= 1 && newPage <= totalPages) {
        setPage(newPage);
      }
    };

    const renderPageNumbers = () => {
      const pageNumbers = [];
      const maxPagesToShow = 5;

      let startPage = Math.max(1, page - Math.floor(maxPagesToShow / 2));
      let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);

      if (endPage - startPage < maxPagesToShow) {
        startPage = Math.max(1, endPage - maxPagesToShow + 1);
      }

      for (let i = startPage; i <= endPage; i++) {
        pageNumbers.push(
          <PaginationItem key={i}>
            <PaginationLink
              href="#"
              onClick={(e) => {
                e.preventDefault();
                changePage(i);
              }}
              className={i === page ? "active" : ""}
              isActive={page === i}
            >
              {i}
            </PaginationLink>
          </PaginationItem>
        );
      }

      return pageNumbers;
    };

    return (
      <div className="w-full">
        <div className="mx-auto flex w-full text-xs text-muted-foreground">
          Showing&nbsp;<strong>{firstPageItem}</strong>-
          <strong>{lastPageItem}</strong>&nbsp;of&nbsp;
          <strong>{totalItems}</strong>&nbsp;records
        </div>
        <Pagination>
          <PaginationContent>
            <PaginationItem>
              <PaginationLink
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  changePage(1);
                }}
                className={page === 1 ? "disabled" : ""}
              >
                First
              </PaginationLink>
            </PaginationItem>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  changePage(page - 1);
                }}
                className={page === 1 ? "disabled" : ""}
              />
            </PaginationItem>
            {renderPageNumbers()}
            {totalPages > 5 && page + 3 < totalPages && <PaginationEllipsis />}
            {totalPages > 5 && page + 2 < totalPages && (
              <PaginationItem>
                <PaginationLink
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    changePage(totalPages);
                  }}
                  className={page === totalPages ? "disabled" : ""}
                >
                  {totalPages}
                </PaginationLink>
              </PaginationItem>
            )}
            <PaginationItem>
              <PaginationNext
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  changePage(page + 1);
                }}
                className={page === totalPages ? "disabled" : ""}
              />
            </PaginationItem>
            <PaginationItem>
              <PaginationLink
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  changePage(totalPages);
                }}
                className={page === totalPages ? "disabled" : ""}
              >
                Last
              </PaginationLink>
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      </div>
    );
  };

  return {
    page,
    setPage,
    PaginationButtons,
  };
}
