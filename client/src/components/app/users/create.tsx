import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { copyToClipboard, trpc } from "@/utils";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useLocation } from "wouter";
import { z } from "zod";

import { Copy } from "lucide-react";
import { useState } from "react";

const FormSchema = z.object({
  name: z.string().min(2),
  email: z.string().email().min(3).max(400),
});

export default function CreateUser() {
  const [generatedPasswordOpen, setGeneratedPasswordOpen] = useState(false);
  const [generatedPassword, setGeneratedPassword] = useState<
    string | undefined
  >(undefined);
  const createUser = trpc.users.create.useMutation();
  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      name: "",
      email: "",
    },
  });
  const [_location, navigate] = useLocation();

  async function onSubmit(data: z.infer<typeof FormSchema>) {
    const result = await createUser.mutateAsync(data);
    setGeneratedPassword(result.generatedPassword);
    setGeneratedPasswordOpen(true);
  }

  async function copyPassword() {
    await copyToClipboard(generatedPassword!);
  }

  function onClosePassword(open: boolean) {
    if (!open) {
      setGeneratedPassword(undefined);
      form.reset();
      setGeneratedPasswordOpen(false);
      navigate("~/users");
    }
  }

  // Update component with organization list selection
  // for the new user inferred from the current user
  // org+roles

  return (
    <>
      <h1 className="text-lg font-semibold md:text-2xl">Create user</h1>
      <div>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="w-full space-y-6"
          >
            <div className="grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
              <Card>
                <CardHeader>
                  <CardDescription>User details</CardDescription>
                </CardHeader>
                <CardContent className="grid gap-4">
                  <div className="grid gap-2">
                    <FormField
                      control={form.control}
                      name="name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Name</FormLabel>
                          <FormControl>
                            <Input placeholder="User's full name" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                  <div className="grid gap-2">
                    <FormField
                      control={form.control}
                      name="email"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Email</FormLabel>
                          <FormControl>
                            <Input
                              placeholder="example@example.com"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </CardContent>
              </Card>
            </div>
            <Button
              type="submit"
              disabled={createUser.isLoading ? true : undefined}
            >
              Create user
            </Button>
          </form>
        </Form>

        <Dialog open={generatedPasswordOpen} onOpenChange={onClosePassword}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Generated password</DialogTitle>
              <DialogDescription>
                The user was created successfully. <br />
                The following password has been generated. It will only be shown
                once:
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-center space-x-2">
              <div className="grid flex-1 gap-2">
                <Label htmlFor="password" className="sr-only">
                  Password
                </Label>
                <Input id="password" value={generatedPassword} readOnly />
              </div>
              <Button
                type="submit"
                size="sm"
                className="px-3"
                onClick={copyPassword}
              >
                <span className="sr-only">Copy</span>
                <Copy className="h-4 w-4" />
              </Button>
            </div>
            <DialogFooter className="sm:justify-start">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Close
                </Button>
              </DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </>
  );
}
