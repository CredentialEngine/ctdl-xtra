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
import { useToast } from "@/components/ui/use-toast";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { trpc } from "@/utils";
import { CatalogueType } from "@common/types";
import { useEffect } from "react";
import { useLocation } from "wouter";

const FormSchema = z.object({
  name: z.string().min(2, {
    message: "Catalogue name must be at least 2 characters.",
  }),
  catalogueType: z.nativeEnum(CatalogueType),
  url: z
    .string()
    .url("Catalogue URL must be a valid URL (e.g. https://example.com)."),
});

export default function CreateCatalogue() {
  const [_location, navigate] = useLocation();
  const { toast } = useToast();
  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      name: "",
      url: "",
      catalogueType: CatalogueType.COURSES,
    },
  });

  const url = form.watch("url");

  const previewQuery = trpc.catalogues.preview.useQuery(
    { url },
    { enabled: false }
  );
  const createMutation = trpc.catalogues.create.useMutation();

  useEffect(() => {
    if (z.string().url().safeParse(url).success) {
      previewQuery.refetch().then((output) => {
        if (output.data?.title) {
          form.setValue("name", output.data.title);
        }
        if (output.data?.catalogueType) {
          form.setValue("catalogueType", output.data.catalogueType);
        }
      });
    }
  }, [url]);

  async function onSubmit(data: z.infer<typeof FormSchema>) {
    try {
      const result = await createMutation.mutateAsync({
        ...data,
        catalogueType: data.catalogueType,
        thumbnailUrl: previewQuery.data?.thumbnailUrl,
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
                  <Select onValueChange={field.onChange} value={field.value}>
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
                    </SelectContent>
                  </Select>
                  <FormDescription>Type of catalogue to create</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            {previewQuery.data?.thumbnailUrl ? (
              <div className="flex gap-4 rounded-lg border border-dashed p-4">
                <img
                  src={previewQuery.data.thumbnailUrl}
                  style={{ maxHeight: "30px" }}
                />
                <div>
                  <h2 className="text-sm font-semibold">
                    {previewQuery.data.title}
                  </h2>
                  <p>{previewQuery.data.description}</p>
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
