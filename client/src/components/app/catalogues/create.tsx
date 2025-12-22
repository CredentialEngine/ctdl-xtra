import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn, trpc } from "@/utils";
import { Check, ChevronsUpDown } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "wouter";
import { CatalogueType } from "../../../../../common/types";

const FormSchema = z.object({
  name: z.string().min(2, {
    message: "Catalogue name must be at least 2 characters.",
  }),
  catalogueType: z.nativeEnum(CatalogueType),
  institutionId: z
    .number({ required_error: "Select an institution" })
    .int()
    .positive({
      message: "Select an institution",
    }),
  url: z
    .string()
    .url("Catalogue URL must be a valid URL (e.g. https://example.com)."),
});

export default function CreateCatalogue() {
  const [, navigate] = useLocation();
  const { toast } = useToast();
  const { institutionId } = useParams();
  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      name: "",
      url: "",
      institutionId: institutionId
        ? parseInt(institutionId)
        : undefined,
      catalogueType: CatalogueType.COURSES,
    },
  });

  const url = form.watch("url");
  const [institutionOpen, setInstitutionOpen] = useState(false);
  const [lastPreviewUrl, setLastPreviewUrl] = useState<string | null>(null);

  const previewQuery = trpc.catalogues.preview.useQuery(
    { url },
    { enabled: false }
  );
  const urlIsValid = z.string().url().safeParse(url).success;
  const institutionsQuery = trpc.institutions.list.useQuery({
    page: 1,
    limit: 200,
    url: urlIsValid ? url : undefined,
  });
  const createMutation = trpc.catalogues.create.useMutation();
  const [institutionSearch, setInstitutionSearch] = useState("");
  const filteredInstitutions = useMemo(() => {
    const term = institutionSearch.trim().toLowerCase();
    if (!term) return institutionsQuery.data?.results || [];
    return (
      institutionsQuery.data?.results.filter((institution) => {
        const inName = institution.name.toLowerCase().includes(term);
        const inDomain = institution.domains.some((d) =>
          d.toLowerCase().includes(term)
        );
        return inName || inDomain;
      }) || []
    );
  }, [institutionSearch, institutionsQuery.data?.results]);

  useEffect(() => {
    const parsed = z.string().url().safeParse(url);
    if (!parsed.success) return;
    if (lastPreviewUrl === url) return;

    setLastPreviewUrl(url);
    previewQuery.refetch().then((output) => {
      const data = output.data;
      if (data && 'title' in data && typeof data.title === 'string' && data.title) {
        form.setValue("name", data.title, { shouldValidate: false });
      }
      if (data && 'catalogueType' in data && data.catalogueType) {
        form.setValue("catalogueType", data.catalogueType as CatalogueType, {
          shouldValidate: false,
        });
      }
    });
  }, [form, previewQuery.refetch, url, lastPreviewUrl]);

  async function onSubmit(data: z.infer<typeof FormSchema>) {
    try {
      const previewData = previewQuery.data;
      const thumbnailUrl = previewData && 'thumbnailUrl' in previewData && typeof previewData.thumbnailUrl === 'string'
        ? previewData.thumbnailUrl 
        : undefined;
      const result = await createMutation.mutateAsync({
        ...data,
        catalogueType: data.catalogueType,
        thumbnailUrl,
      });
      form.reset();
      if (result.existing) {
        toast({
          title: "Catalogue already exists",
          description: "Catalogue already exists, redirecting to it.",
        });
        navigate(`/${result.id}`);
      } else {
        toast({
          title: "Catalogue saved",
          description:
            "Catalogue saved successfully! Now let's set up an extraction recipe.",
        });
        navigate(`/${result.id}/recipes/new`);
      }
    } catch (error: unknown) {
      const description =
        error instanceof Error ? error.message : JSON.stringify(error);
      toast({
        title: "Error saving catalogue",
        description,
      });
    }
  }

  return (
    <>
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Add new catalogue</h1>
      </div>
      <div className="" x-chunk="dashboard-02-chunk-1">
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="w-2/3 space-y-6"
          >
            <FormField
              control={form.control}
              name="url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>URL</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="http://www.example.com/course_catalogue"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>URL for the catalogue</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="name"
              disabled={previewQuery.isFetching ? true : undefined}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Catalogue Name" {...field} />
                  </FormControl>
                  <FormDescription>
                    Display name for the catalogue
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="catalogueType"
              disabled={previewQuery.isFetching ? true : undefined}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Type</FormLabel>
                  <Select
                    onValueChange={(value) => {
                      field.onChange(value as CatalogueType);
                    }}
                    value={field.value}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select a type" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value={CatalogueType.COURSES}>
                        Courses
                      </SelectItem>
                      <SelectItem value={CatalogueType.LEARNING_PROGRAMS}>
                        Learning Programs
                      </SelectItem>
                      <SelectItem value={CatalogueType.COMPETENCIES}>
                        Competencies
                      </SelectItem>
                      <SelectItem value={CatalogueType.CREDENTIALS}>
                        Credentials
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>Type of catalogue to create</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="institutionId"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Institution</FormLabel>
                  <Popover open={institutionOpen} onOpenChange={setInstitutionOpen}>
                    <PopoverTrigger asChild>
                      <FormControl>
                        <Button
                          variant="outline"
                          role="combobox"
                          aria-expanded={institutionOpen}
                          className="w-full justify-between"
                        >
                          {field.value
                            ? filteredInstitutions.find(
                                (institution) => institution.id === field.value
                              )?.name || "Select an institution"
                            : "Select an institution"}
                          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                      </FormControl>
                    </PopoverTrigger>
                    <PopoverContent className="w-[540px] p-0">
                      <Command>
                        <CommandInput
                          placeholder="Search institutions..."
                          value={institutionSearch}
                          onValueChange={setInstitutionSearch}
                        />
                        <CommandList>
                          <CommandEmpty>
                            {institutionsQuery.isLoading
                              ? "Loading institutions..."
                              : "No institutions found"}
                          </CommandEmpty>
                          <CommandGroup>
                            {filteredInstitutions.map((institution) => (
                              <CommandItem
                                key={institution.id}
                                value={institution.name}
                                onSelect={() => {
                                  field.onChange(institution.id);
                                  setInstitutionOpen(false);
                                }}
                              >
                                <Check
                                  className={cn(
                                    "mr-2 h-4 w-4",
                                    field.value === institution.id
                                      ? "opacity-100"
                                      : "opacity-0"
                                  )}
                                />
                                <div className="flex flex-col">
                                  <span>{institution.name}</span>
                                  <span className="text-xs text-muted-foreground">
                                    {institution.domains.join(", ")}
                                  </span>
                                </div>
                              </CommandItem>
                            ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                  <FormDescription>
                    Institutions that match the catalogue URL appear first.{" "}
                    <Link to="~/institutions/new" className="underline">
                      Create a new institution
                    </Link>{" "}
                    if you don't see yours.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            {previewQuery.data && 'thumbnailUrl' in previewQuery.data && typeof previewQuery.data.thumbnailUrl === 'string' && previewQuery.data.thumbnailUrl ? (
              <div className="flex gap-4 rounded-lg border border-dashed p-4">
                <img
                  src={previewQuery.data.thumbnailUrl}
                  style={{ maxHeight: "30px" }}
                />
                <div>
                  <h2 className="text-sm font-semibold">
                    {'title' in previewQuery.data && typeof previewQuery.data.title === 'string' ? previewQuery.data.title : ''}
                  </h2>
                  <p>{'description' in previewQuery.data && typeof previewQuery.data.description === 'string' ? previewQuery.data.description : ''}</p>
                </div>
              </div>
            ) : null}
            <Button
              type="submit"
              disabled={createMutation.isLoading ? true : undefined}
            >
              Submit
            </Button>
          </form>
        </Form>
      </div>
    </>
  );
}
