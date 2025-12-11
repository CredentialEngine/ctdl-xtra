import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { trpc } from "@/utils";
import { Plus, Search, University } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "wouter";
import usePagination from "../usePagination";

function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout;
  return (...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

const InstitutionRow = ({
  id,
  name,
  domains,
  catalogueCount,
}: {
  id: number;
  name: string;
  domains: string[];
  catalogueCount: number;
}) => {
  return (
    <TableRow>
      <TableCell className="font-medium">
        <Link to={`/${id}`}>{name}</Link>
      </TableCell>
      <TableCell className="hidden md:table-cell">
        <div className="flex flex-wrap gap-2">
          {domains.map((domain) => (
            <Badge key={`${id}-${domain}`} variant="secondary">
              {domain}
            </Badge>
          ))}
        </div>
      </TableCell>
      <TableCell className="hidden md:table-cell text-muted-foreground">
        {catalogueCount} catalogue{catalogueCount === 1 ? "" : "s"}
      </TableCell>
    </TableRow>
  );
};

export default function Institutions() {
  const { page, setPage, PaginationButtons } = usePagination();
  const [search, setSearch] = useState("");
  const debouncedSetSearch = useRef(debounce(setSearch, 300)).current;
  const listQuery = trpc.institutions.list.useQuery({
    page,
    search,
    limit: 20,
  });

  const handleSearchChange = (value: string) => {
    setPage(1);
    debouncedSetSearch(value);
  };

  const searchFilters = (
    <div className="relative flex-1 max-w-lg">
      <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
      <Input
        placeholder="Search institutions by name or domain..."
        className="pl-8"
        onChange={(e) => handleSearchChange(e.target.value)}
      />
    </div>
  );

  if (listQuery.isFetched && !listQuery.data?.results.length) {
    return (
      <>
        <div className="flex items-center">
          <h1 className="text-lg font-semibold md:text-2xl">Institutions</h1>
        </div>
        {searchFilters}
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed shadow-sm">
          <div className="flex flex-col items-center gap-1 text-center p-8">
            <University className="h-10 w-10 text-muted-foreground" />
            <h3 className="text-2xl font-bold tracking-tight">
              No institutions yet
            </h3>
            <p className="text-sm text-muted-foreground">
              Add an institution to group catalogues by organization.
            </p>
            <Link to="/new">
              <Button className="mt-4">Add Institution</Button>
            </Link>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="w-full flex justify-between items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Institutions</h1>
        <Link to={"/new"}>
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            Add institution
          </Button>
        </Link>
      </div>
      <div className="mt-2">{searchFilters}</div>
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Institution</TableHead>
                <TableHead className="hidden md:table-cell">
                  Domains
                </TableHead>
                <TableHead className="hidden md:table-cell">
                  Catalogues
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {listQuery.data?.results.map((institution) => (
                <InstitutionRow key={institution.id} {...institution} />
              )) || (
                <TableRow>
                  <TableCell colSpan={3}>
                    <div className="flex items-center justify-center">
                      <span className="text-muted-foreground">
                        Loading institutions...
                      </span>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
        {listQuery.data?.results.length ? (
          <CardFooter>
            <PaginationButtons
              totalItems={listQuery.data.totalItems}
              totalPages={listQuery.data.totalPages}
            />
          </CardFooter>
        ) : null}
      </Card>
    </>
  );
}
