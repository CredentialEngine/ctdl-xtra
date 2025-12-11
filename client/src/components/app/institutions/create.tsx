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
import { trpc } from "@/utils";
import { useEffect } from "react";
import { useLocation } from "wouter";

const FormSchema = z.object({
  name: z.string().min(2, {
    message: "Institution name must be at least 2 characters.",
  }),
  domains: z.string().min(3, {
    message: "Add at least one domain (e.g. example.edu).",
  }),
});

function parseDomains(domains: string) {
  return domains
    .split(/[,\\n]/)
    .map((domain) => domain.trim())
    .filter(Boolean);
}

const domainRegex = /^(?!-)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/;

export default function CreateInstitution() {
  const [, navigate] = useLocation();
  const { toast } = useToast();
  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      name: "",
      domains: "",
    },
  });

  const createMutation = trpc.institutions.create.useMutation();

  useEffect(() => {
    form.setFocus("name");
  }, [form]);

  async function onSubmit(data: z.infer<typeof FormSchema>) {
    const parsedDomains = parseDomains(data.domains);
    const invalid = parsedDomains.filter((domain) => !domainRegex.test(domain));
    if (invalid.length || !parsedDomains.length) {
      form.setError("domains", {
        message: invalid.length
          ? `Invalid domain(s): ${invalid.join(", ")}`
          : "Add at least one domain.",
      });
      return;
    }
    try {
      const result = await createMutation.mutateAsync({
        name: data.name,
        domains: parsedDomains,
      });
      form.reset();
      toast({
        title: "Institution created",
        description: "You can now create catalogues for this institution.",
      });
      navigate(`~/institutions/${result.id}`);
    } catch (error: unknown) {
      const description =
        error instanceof Error ? error.message : JSON.stringify(error);
      toast({
        title: "Error creating institution",
        description,
      });
    }
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold md:text-2xl">
          Add new institution
        </h1>
      </div>
      <div className="mt-4">
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="w-2/3 space-y-6"
          >
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="University of Example" {...field} />
                  </FormControl>
                  <FormDescription>
                    The institution name users will see when assigning
                    catalogues.
                  </FormDescription>
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
                    <Input
                      placeholder="example.edu, courses.example.edu"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    Comma-separated list of domains used by this institution.
                    These help auto-suggest institutions when creating or
                    reassigning catalogues.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button
              type="submit"
              disabled={createMutation.isLoading ? true : undefined}
            >
              Save
            </Button>
          </form>
        </Form>
      </div>
    </>
  );
}
