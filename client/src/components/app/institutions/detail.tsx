import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { prettyPrintDate, trpc } from "@/utils";
import { Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "wouter";
import { parseDomains, validateDomains } from "../../../../../common/domains";

const FormSchema = z.object({
  name: z.string().min(2, {
    message: "Institution name must be at least 2 characters.",
  }),
  domains: z.string().min(3, {
    message: "Add at least one domain.",
  }),
});

export default function InstitutionDetail() {
  const { institutionId } = useParams();
  const [, navigate] = useLocation();
  const { toast } = useToast();
  const [lockedDelete, setLockedDelete] = useState(true);
  const detailQuery = trpc.institutions.detail.useQuery(
    { id: parseInt(institutionId || "") },
    { enabled: !!parseInt(institutionId || "") }
  );
  const updateMutation = trpc.institutions.update.useMutation();
  const destroyMutation = trpc.institutions.destroy.useMutation();
  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      name: "",
      domains: "",
    },
  });

  useEffect(() => {
    if (detailQuery.data) {
      form.reset({
        name: detailQuery.data.name,
        domains: detailQuery.data.domains.join(", "),
      });
    }
  }, [detailQuery.data, form]);

  if (!detailQuery.data) {
    return null;
  }

  const institution = detailQuery.data;
  const catalogues = institution.catalogues || [];

  async function onSubmit(values: z.infer<typeof FormSchema>) {
    const parsedDomains = parseDomains(values.domains);
    const { normalized, invalid } = validateDomains(parsedDomains);
    if (invalid.length || !normalized.length) {
      form.setError("domains", {
        message: invalid.length
          ? `Invalid domain(s): ${invalid.join(", ")}`
          : "Add at least one domain.",
      });
      return;
    }
    await updateMutation.mutateAsync({
      id: institution.id,
      name: values.name,
      domains: normalized,
    });
    toast({
      title: "Institution updated",
      description: "Changes saved successfully.",
    });
    await detailQuery.refetch();
  }

  const destroyInstitution = async () => {
    try {
      await destroyMutation.mutateAsync({ id: institution.id });
      toast({
        title: "Institution deleted",
        description: "The institution has been removed.",
      });
      navigate("~/institutions");
    } catch (error: unknown) {
      const description =
        error instanceof Error ? error.message : JSON.stringify(error);
      toast({
        title: "Unable to delete institution",
        description,
      });
    }
  };

  return (
    <>
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-lg font-semibold md:text-2xl">
            {institution.name}
          </h1>
          <div className="text-sm text-muted-foreground">
            Created {prettyPrintDate(institution.createdAt)}
          </div>
        </div>
        <Link to={`~/catalogues/new/${institution.id}`}>
          <Button>Add catalogue</Button>
        </Link>
      </div>
      <div className="grid gap-4 md:grid-cols-[1fr] lg:grid-cols-3 lg:gap-8">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Institution details</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Name</FormLabel>
                      <FormControl>
                        <Input placeholder="Institution name" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="domains"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Domains</FormLabel>
                      <FormControl>
                        <Input placeholder="example.edu, school.example.edu" {...field} />
                      </FormControl>
                      <FormDescription>
                        Comma-separated list of domains used by this institution.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="flex gap-2">
                  <Button
                    type="submit"
                    disabled={updateMutation.isLoading ? true : undefined}
                  >
                    Save changes
                  </Button>
                  <Dialog>
                    <DialogTrigger asChild>
                      <Button variant="destructive" size="icon">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>Delete institution?</DialogTitle>
                        <DialogDescription>
                          Deleting an institution requires reassigning all
                          catalogues first.
                        </DialogDescription>
                      </DialogHeader>
                      <div className="flex items-center space-x-2">
                        <Checkbox
                          id="confirm-delete"
                          onCheckedChange={(checked) =>
                            setLockedDelete(checked !== true)
                          }
                        />
                        <label htmlFor="confirm-delete" className="text-sm">
                          I understand this action cannot be undone.
                        </label>
                      </div>
                      <Button
                        variant="destructive"
                        disabled={lockedDelete || destroyMutation.isLoading}
                        onClick={destroyInstitution}
                      >
                        Delete institution
                      </Button>
                    </DialogContent>
                  </Dialog>
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Catalogues</CardTitle>
            <Link to={`~/catalogues/new/${institution.id}`}>
              <Button variant="outline">Add catalogue</Button>
            </Link>
          </CardHeader>
          <CardContent>
            {catalogues.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Catalogue</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead className="hidden md:table-cell">URL</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {catalogues.map((catalogue) => (
                    <TableRow key={`catalogue-${catalogue.id}`}>
                      <TableCell className="font-medium">
                        <Link to={`~/catalogues/${catalogue.id}`}>
                          {catalogue.name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {catalogue.catalogueType}
                        </Badge>
                      </TableCell>
                      <TableCell className="hidden md:table-cell text-muted-foreground">
                        {catalogue.url}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="outline" size="sm" asChild>
                          <Link to={`~/catalogues/${catalogue.id}`}>
                            View
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                No catalogues yet.{" "}
                <Link
                  to={`~/catalogues/new/${detailQuery.data.id}`}
                  className="underline"
                >
                  Create one now
                </Link>
                .
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
